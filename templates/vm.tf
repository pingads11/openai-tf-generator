provider "aws" {
  region = "eu-central-1"
}

variable "target_account_name" {
  type        = string
}

data "aws_vpc" "selected" {
  filter {
    name   = "tag:Name"
    values = ["${var.target_account_name}-VPC"]
  }
}

data "aws_subnet" "selected" {
  vpc_id = data.aws_vpc.selected.id

  filter {
    name   = "tag:Name"
    values = ["${var.target_account_name}-Tier2-private-1a"]
  }
}

data "aws_ami" "linux" {
  most_recent = true

  filter {
    name   = "name"
    values = ["goldenlinuxrh8 *"]
  }
}

resource "aws_instance" "this" {
  ami                    = data.aws_ami.linux.id
  subnet_id              = data.aws_subnet.selected.id
}