#!/usr/bin/env python3
import os  # noqa: F401

import aws_cdk as cdk

from infrastructure.infrastructure_stack import TestStack


app = cdk.App()
TestStack(app, "TestStack")

app.synth()
