variable "aws_region" {
  description = "AWS region everything is deployed in."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for every resource name - matches what you already created by hand (assessment4-robert-*)."
  type        = string
  default     = "assessment4-robert"
}

variable "eks_kubernetes_version" {
  description = "Kubernetes control plane version."
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS worker nodes."
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_max_size" {
  type    = number
  default = 3
}
