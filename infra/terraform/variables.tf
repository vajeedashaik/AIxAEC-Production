variable "region" {
  description = "Same region as the hosted Supabase project (Ireland), to keep database round trips short."
  type        = string
  default     = "eu-west-1"
}

variable "image_tag" {
  description = "Written to image.auto.tfvars by scripts/build-push.ps1."
  type        = string
  default     = "not-built"
}

variable "alert_email" {
  description = "Receives job notifications and alarms. AWS sends one confirmation email first."
  type        = string
}

variable "api_ingress_cidr" {
  description = "Who may reach :8000. Use your own IP as x.x.x.x/32: the API is plain HTTP, so tokens travel unencrypted."
  type        = string

  validation {
    condition     = can(cidrhost(var.api_ingress_cidr, 0))
    error_message = "Must be a CIDR block such as 203.0.113.7/32."
  }
}

variable "web_origin" {
  description = "Origin of the web app, for CORS and Clerk's authorized parties."
  type        = string
  default     = "http://localhost:3000"
}

variable "ocr_provider" {
  description = "OCR for floor-plan labels: tesseract (free, bundled), rekognition (works on the Free Plan), or textract (needs a paid plan)."
  type        = string
  default     = "tesseract"

  validation {
    condition     = contains(["tesseract", "rekognition", "textract"], var.ocr_provider)
    error_message = "ocr_provider must be tesseract, rekognition or textract."
  }
}

variable "stt_provider" {
  description = "Speech-to-text for voice commands: whisper (free, runs in the language container) or transcribe (needs an AWS plan that allows it; the Free Plan returns SubscriptionRequiredException)."
  type        = string
  default     = "whisper"

  validation {
    condition     = contains(["whisper", "transcribe"], var.stt_provider)
    error_message = "stt_provider must be whisper or transcribe."
  }
}

variable "bedrock_model_id" {
  description = "Optional. A Bedrock model or inference profile ID enabled in this account and region. Empty means no LLM: the offline rules parser handles commands."
  type        = string
  default     = ""

  validation {
    condition     = var.bedrock_model_id == "" || can(regex("^[a-z0-9.:-]+$", var.bedrock_model_id))
    error_message = "Leave empty, or set a real Bedrock model ID (lowercase, such as eu.amazon.nova-2-lite-v1:0)."
  }
}

variable "database_url" {
  description = "Supabase transaction-pooler URL (postgresql+psycopg://...)."
  type        = string
  sensitive   = true
}

variable "worker_database_url" {
  description = "Supabase session-pooler URL: the worker relies on FOR UPDATE SKIP LOCKED."
  type        = string
  sensitive   = true
}

variable "supabase_url" {
  type = string
}

variable "supabase_service_role_key" {
  type      = string
  sensitive = true
}

variable "clerk_issuer" {
  type = string
}

variable "clerk_secret_key" {
  type      = string
  sensitive = true
}

variable "internal_service_token" {
  description = "At least 32 characters: the services refuse to start in production otherwise."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.internal_service_token) >= 32
    error_message = "Must be at least 32 characters."
  }
}
