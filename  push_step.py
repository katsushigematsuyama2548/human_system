import json
import boto3

sfn_client = boto3.client('stepfunctions')

STATE_MACHINE_ARN = "arn:aws:states:us-west-2:571600859121:stateMachine:test"

def lambda_handler(event, context):
    input_data = {
        "message": "Step Functions 実行開始の入力データサンプル",
        "callbackInfo": "必要な追加情報"
    }
    
    try:
        response = sfn_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(input_data)
        )
        execution_arn = response['executionArn']
        print("Step Functions execution started:", execution_arn)
    except Exception as e:
        print("Error starting Step Functions:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps("Step Functions の実行開始に失敗しました")
        }
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Step Functions の実行開始に成功しました",
            "executionArn": execution_arn
        })
    }