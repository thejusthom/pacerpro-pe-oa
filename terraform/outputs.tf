output "instance_id" {
  value       = aws_instance.web.id
  description = "The ID of the EC2 instance."
}
output "sns_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "The ARN of the SNS topic for alerts."
}
output "lambda_function_name" {
  value       = aws_lambda_function.instance_rebooter.function_name
  description = "The name of the Lambda function for auto-remediation."
}