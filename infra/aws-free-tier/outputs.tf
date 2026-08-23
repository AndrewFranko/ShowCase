output "portal_url" {
  description = "Where the portal answers (behind basic-auth)."
  value       = var.domain != "" ? "https://${var.domain}" : "https://${aws_eip.portal.public_ip}"
}

output "public_ip" {
  value = aws_eip.portal.public_ip
}

output "instance_id" {
  description = "For SSM sessions: aws ssm start-session --target <id>"
  value       = aws_instance.portal.id
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.bucket
}

output "verify_command" {
  description = "The same gate as every other deploy in this project."
  value = join(" ", [
    "DEPLOY_BASE=${var.domain != "" ? "https://${var.domain}" : "https://${aws_eip.portal.public_ip}"}",
    "DEPLOY_AUTH=${var.basic_auth_user}:<password>",
    "pytest tests/e2e/test_deployed.py -q",
  ])
}
