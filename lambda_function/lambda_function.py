import os
import json
import base64
import boto3
from datetime import datetime, timezone

ec2 = boto3.client("ec2")
sns = boto3.client("sns")


def _safe_json(obj, limit=2000):
    try:
        s = json.dumps(obj, default=str)
        return s[:limit]
    except Exception:
        return str(obj)[:limit]


def _payload_from_event(event):
    if isinstance(event, dict) and "body" in event:
        body = event.get("body")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        if isinstance(body, str) and body.strip():
            try:
                return json.loads(body)
            except Exception:
                return {"raw_body": body}
        return {}
    return event if isinstance(event, dict) else {}


def lambda_handler(event, context):
    instance_id = os.environ["INSTANCE_ID"]
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]

    expected_secret = os.environ.get("WEBHOOK_SECRET")
    headers = (event.get("headers") if isinstance(event, dict) else {}) or {}
    provided_secret = headers.get("x-webhook-secret") or headers.get("X-Webhook-Secret")

    if expected_secret and provided_secret != expected_secret:
        print(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "webhook_rejected",
            "reason": "invalid_or_missing_secret",
        }))
        return {"statusCode": 401, "body": json.dumps({"ok": False, "message": "Unauthorized"})}

    payload = _payload_from_event(event)

    alert_name = payload.get("monitorName") or payload.get("alert_name") or "unknown-alert"
    source_host = payload.get("sourceHost") or payload.get("_sourceHost") or "unknown-host"
    slow_calls = payload.get("slow_calls") or payload.get("count") or "unknown-count"
    timeslice = payload.get("timeslice") or payload.get("_timeslice") or "unknown-timeslice"

    now = datetime.now(timezone.utc).isoformat()

    print(json.dumps({
        "ts": now,
        "action": "auto_remediation_start",
        "instance_id": instance_id,
        "alert_name": alert_name,
        "source_host": source_host,
        "slow_calls": slow_calls,
        "timeslice": timeslice,
        "request_id": getattr(context, "aws_request_id", None),
    }))

    try:
        ec2.reboot_instances(InstanceIds=[instance_id])

        message_obj = {
            "ts": now,
            "result": "reboot_initiated",
            "instance_id": instance_id,
            "alert_name": alert_name,
            "source_host": source_host,
            "slow_calls": slow_calls,
            "timeslice": timeslice,
            "raw_payload_truncated": _safe_json(payload, limit=1200),
        }

        sns.publish(
            TopicArn=sns_topic_arn,
            Subject="Auto-Remediation Triggered",
            Message=_safe_json(message_obj, limit=8000),
        )

        return {
            "statusCode": 200,
            "body": json.dumps({"ok": True, "message": "Reboot initiated", "instance_id": instance_id}),
        }

    except Exception as e:
        print(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "auto_remediation_error",
            "instance_id": instance_id,
            "error": str(e),
        }))

        try:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject="Auto-Remediation FAILED",
                Message=_safe_json({"ok": False, "instance_id": instance_id, "error": str(e)}, limit=8000),
            )
        except Exception:
            pass

        return {
            "statusCode": 500,
            "body": json.dumps({"ok": False, "message": "Remediation failed", "error": str(e)}),
        }