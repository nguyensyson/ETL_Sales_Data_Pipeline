# ---------------------------------------------------------------------------
# AWS Step Functions — Pipeline State Machine
#
# Workflow steps (mirrors architecture diagram):
#   1. ValidateCSV          (Lambda invoke)           — step 4
#   2. StartRawCrawler      (Glue startCrawler)       — step 6
#   3. WaitForRawCrawler    (Wait 30s)
#   4. CheckRawCrawler      (Lambda poll GetCrawler)
#   5. RawCrawlerDone?      (Choice — READY / loop)
#   6. RunGlueETL           (Glue startJobRun.sync)   — step 7
#   7. StartProcessedCrawler(Glue startCrawler)       — step 9
#   8. WaitForProcCrawler   (Wait 30s)
#   9. CheckProcCrawler     (Lambda poll GetCrawler)
#  10. ProcCrawlerDone?     (Choice — READY / loop)
#  11. NotifySuccess        (SNS)                     — step 11
#  On any failure → NotifyFailure (SNS) → PipelineFailed
#
# NOTE: Step Functions does NOT support glue:startCrawler.sync —
#       only glue:startJobRun.sync is available. Crawlers must be
#       polled manually using a Wait + Choice loop pattern.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "sfn" {
  name              = local.cloudwatch_log_group
  retention_in_days = 30
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = local.step_function_name
  role_arn = aws_iam_role.step_functions.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  definition = jsonencode({
    Comment = "ShopMart daily sales data pipeline"
    StartAt = "ValidateCSV"

    States = {

      # ── Step 4: Lambda CSV validation ──────────────────────────────────
      ValidateCSV = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.csv_validator.arn
          "Payload.$"  = "$"
        }
        ResultSelector = {
          "body.$" = "$.Payload"
        }
        ResultPath = "$.validationResult"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "StartRawCrawler"
      }

      # ── Step 6a: Start Glue Crawler on staged data ──────────────────────
      # glue:startCrawler does NOT support .sync — fire and poll manually.
      StartRawCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:startCrawler"
        Parameters = {
          Name = aws_glue_crawler.raw.name
        }
        ResultPath = null
        Catch = [{
          # CrawlerRunningException means it is already running — treat as OK
          ErrorEquals = ["Glue.CrawlerRunningException"]
          Next        = "WaitForRawCrawler"
          ResultPath  = null
        }, {
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "WaitForRawCrawler"
      }

      # ── Step 6b: Wait before polling crawler status ──────────────────────
      WaitForRawCrawler = {
        Type    = "Wait"
        Seconds = 30
        Next    = "CheckRawCrawlerStatus"
      }

      # ── Step 6c: Poll crawler state via SDK integration ──────────────────
      CheckRawCrawlerStatus = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:getCrawler"
        Parameters = {
          Name = aws_glue_crawler.raw.name
        }
        ResultSelector = {
          "State.$" = "$.Crawler.State"
        }
        ResultPath = "$.rawCrawlerStatus"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "IsRawCrawlerReady"
      }

      # ── Step 6d: Branch — loop until crawler is READY ───────────────────
      IsRawCrawlerReady = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.rawCrawlerStatus.State"
          StringEquals = "READY"
          Next         = "RunGlueETL"
        }]
        # Still RUNNING or STOPPING — wait again
        Default = "WaitForRawCrawler"
      }

      # ── Step 7: Glue ETL Job (.sync is valid for Jobs) ───────────────────
      RunGlueETL = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = aws_glue_job.etl.name
        }
        ResultPath = "$.glueJobResult"
        Retry = [{
          ErrorEquals     = ["Glue.ConcurrentRunsExceededException"]
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "StartProcessedCrawler"
      }

      # ── Step 9a: Start Glue Crawler on processed Parquet ─────────────────
      StartProcessedCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:startCrawler"
        Parameters = {
          Name = aws_glue_crawler.processed.name
        }
        ResultPath = null
        Catch = [{
          ErrorEquals = ["Glue.CrawlerRunningException"]
          Next        = "WaitForProcessedCrawler"
          ResultPath  = null
        }, {
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "WaitForProcessedCrawler"
      }

      # ── Step 9b: Wait before polling ─────────────────────────────────────
      WaitForProcessedCrawler = {
        Type    = "Wait"
        Seconds = 30
        Next    = "CheckProcessedCrawlerStatus"
      }

      # ── Step 9c: Poll processed crawler state ────────────────────────────
      CheckProcessedCrawlerStatus = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:getCrawler"
        Parameters = {
          Name = aws_glue_crawler.processed.name
        }
        ResultSelector = {
          "State.$" = "$.Crawler.State"
        }
        ResultPath = "$.processedCrawlerStatus"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "IsProcessedCrawlerReady"
      }

      # ── Step 9d: Branch — loop until crawler is READY ────────────────────
      IsProcessedCrawlerReady = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.processedCrawlerStatus.State"
          StringEquals = "READY"
          Next         = "NotifySuccess"
        }]
        Default = "WaitForProcessedCrawler"
      }

      # ── Step 11 (success): SNS notification ──────────────────────────────
      # $$.Execution.Name uses the context object ($$), not the input ($)
      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn  = aws_sns_topic.pipeline_alerts.arn
          "Message.$" = "States.Format('ShopMart pipeline completed successfully. Execution: {}', $$.Execution.Name)"
          Subject   = "ShopMart Pipeline — SUCCESS"
        }
        ResultPath = null
        End        = true
      }

      # ── Failure handler: SNS notification ────────────────────────────────
      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn  = aws_sns_topic.pipeline_alerts.arn
          "Message.$" = "States.Format('ShopMart pipeline FAILED. Execution: {}', $$.Execution.Name)"
          Subject   = "ShopMart Pipeline — FAILURE"
        }
        ResultPath = null
        Next       = "PipelineFailed"
      }

      PipelineFailed = {
        Type  = "Fail"
        Error = "PipelineError"
        Cause = "One or more pipeline steps failed. Check SNS notification and CloudWatch Logs for details."
      }
    }
  })
}
