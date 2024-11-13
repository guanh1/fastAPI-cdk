#!/usr/bin/env python3
import os  # noqa: F401

import aws_cdk as cdk

from infrastructure.infrastructure_stack import InfrastructureStack


app = cdk.App()
InfrastructureStack(app, "FastApiCdkStack")

app.synth()
