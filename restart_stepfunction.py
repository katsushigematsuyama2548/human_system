import json
import boto3

sfn_client = boto3.client('stepfunctions')

def lambda_handler(event, context):
    # API Gateway のパスパラメータから taskToken を取得
    params = event.get('pathParameters', {})
    task_token = params.get('tasktoken')  # 注意: パラメーター名は小文字になる可能性あり
  
    if not task_token:
        return {
            "statusCode": 400,
            "body": json.dumps("taskToken がありません")
        }
    
    # ユーザーがクリックしたことを反映するための出力（任意の情報）
    output_data = {"status": "ユーザーがリンクをクリックしました"}
    
    try:
        sfn_client.send_task_success(
            taskToken=task_token,
            output=json.dumps(output_data)
        )
        return {
            "statusCode": 200,
            "body": json.dumps("タスクの再開に成功しました")
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(f"タスク再開に失敗しました: {str(e)}")
        }