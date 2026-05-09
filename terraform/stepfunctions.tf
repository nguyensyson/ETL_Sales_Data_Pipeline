# ---------------------------------------------------------------------------
# AWS Step Functions — Pipeline State Machine
#
# Workflow steps (mirrors architecture diagram):
#   1. ValidateCSV (Lambda)          — step 4
#   2. CrawlRawData (Glue Crawler)   — step 6
#   3. RunGlueETL (Glue Job)         — step 7
#   4. CrawlProcessedData (Crawler)  — step 9
#   5. NotifySuccess (SNS)           — step 11 success path
#   On any failure → NotifyFailure (SNS)
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
        ResultPath = "$.validationResult"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "CrawlRawData"
      }

      # ── Step 6: Glue Crawler — raw/staged data ──────────────────────────
      CrawlRawData = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startCrawler.sync"
        Parameters = {
          Name = aws_glue_crawler.raw.name
        }
        ResultPath = "$.crawlRawResult"
        Retry = [{
          ErrorEquals     = ["Glue.CrawlerRunningException"]
          IntervalSeconds = 30
          MaxAttempts     = 3
          BackoffRate     = 1.5
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "RunGlueETL"
      }

      # ── Step 7: Glue ETL Job ─────────────────────────────────────────────
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
        Next = "CrawlProcessedData"
      }

      # ── Step 9: Glue Crawler — processed Parquet ─────────────────────────
      CrawlProcessedData = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startCrawler.sync"
        Parameters = {
          Name = aws_glue_crawler.processed.name
        }
        ResultPath = "$.crawlProcessedResult"
        Retry = [{
          ErrorEquals     = ["Glue.CrawlerRunningException"]
          IntervalSeconds = 30
          MaxAttempts     = 3
          BackoffRate     = 1.5
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
          ResultPath  = "$.error"
        }]
        Next = "NotifySuccess"
      }

      # ── Step 11 (success): SNS notification ──────────────────────────────
      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = aws_sns_topic.pipeline_alerts.arn
          Message = {
            "Input.$" = "States.Format('Pipeline completed successfully. Execution: {}', $$.Execution.Name)"
          }
          Subject = "ShopMart Pipeline — SUCCESS"
        }
        End = true
      }

      # ── Failure handler: SNS notification ────────────────────────────────
      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = aws_sns_topic.pipeline_alerts.arn
          Message = {
            "Input.$" = "States.Format('Pipeline FAILED. Execution: {}. Error: {}', $$.Execution.Name, $.error)"
          }
          Subject = "ShopMart Pipeline — FAILURE"
        }
        Next = "PipelineFailed"
      }

      PipelineFailed = {
        Type  = "Fail"
        Error = "PipelineError"
        Cause = "One or more pipeline steps failed. Check SNS notification for details."
      }
    }
  })
}
