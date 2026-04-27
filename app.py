#!/usr/bin/env python3
import aws_cdk as cdk
from image_pipeline.pipeline_stack import ImagePipelineStack

app = cdk.App()

ImagePipelineStack(
    app,
    "ImagePipelineStack",
    env=cdk.Environment(
        account="820242933814",
        region="ap-southeast-2",
    ),
)

app.synth()
