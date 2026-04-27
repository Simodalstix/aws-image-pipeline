from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_codebuild as codebuild,
)
from constructs import Construct

# Packer version pinned for reproducible builds. Update when upgrading Packer.
PACKER_VERSION = "1.11.0"

PACKER_INSTALL = [
    f"wget -q -O /tmp/packer.zip https://releases.hashicorp.com/packer/{PACKER_VERSION}/packer_{PACKER_VERSION}_linux_amd64.zip",
    "unzip -q /tmp/packer.zip -d /usr/local/bin",
    "packer init packer/",
]


class ImagePipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Packer builder instance role ---
        # Attached to the EC2 instance Packer launches during builds.
        # Referenced by packer/variables.pkrvars.hcl as iam_instance_profile = "packer-builder".
        builder_role = iam.Role(
            self,
            "PackerBuilderRole",
            role_name="packer-builder",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )

        # Instance profile wrapping the builder role.
        iam.CfnInstanceProfile(
            self,
            "PackerBuilderInstanceProfile",
            instance_profile_name="packer-builder",
            roles=[builder_role.role_name],
        )

        # --- CodeBuild role ---
        # Needs broad EC2 permissions so Packer can launch/terminate builder
        # instances, manage temporary key pairs and security groups, and create AMIs.
        codebuild_role = iam.Role(
            self,
            "PackerCodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:RunInstances",
                    "ec2:TerminateInstances",
                    "ec2:StopInstances",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceStatus",
                    "ec2:CreateImage",
                    "ec2:DescribeImages",
                    "ec2:DeregisterImage",
                    "ec2:CreateTags",
                    "ec2:DescribeTags",
                    "ec2:CreateSecurityGroup",
                    "ec2:DeleteSecurityGroup",
                    "ec2:AuthorizeSecurityGroupIngress",
                    "ec2:RevokeSecurityGroupIngress",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeVpcs",
                    "ec2:CreateKeyPair",
                    "ec2:DeleteKeyPair",
                    "ec2:DescribeKeyPairs",
                    "ec2:DescribeVolumes",
                    "ec2:CreateSnapshot",
                    "ec2:DeleteSnapshot",
                    "ec2:DescribeSnapshots",
                    "ec2:ModifyImageAttribute",
                    "ec2:EnableImageDeprecation",
                    "ec2:DescribeRegions",
                    "ec2:DescribeAvailabilityZones",
                ],
                resources=["*"],
            )
        )

        # Allows CodeBuild to pass the builder instance profile to Packer-launched EC2.
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[builder_role.role_arn],
            )
        )

        ssm_param_base = f"arn:aws:ssm:{self.region}:{self.account}:parameter"
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[
                    f"{ssm_param_base}/ops-lab/networking/*",
                    f"{ssm_param_base}/ops-lab/shared/*",
                    f"{ssm_param_base}/ops-lab/images/*",
                ],
            )
        )
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:PutParameter"],
                resources=[f"{ssm_param_base}/ops-lab/images/*"],
            )
        )

        # --- CodeBuild projects ---
        # Both projects are triggered manually via the console or CLI.
        # Wire to CodePipeline for automated builds on git push (future phase).

        build_env = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            compute_type=codebuild.ComputeType.SMALL,
        )

        codebuild.Project(
            self,
            "BaseAMIBuild",
            project_name="ops-lab-build-base-ami",
            role=codebuild_role,
            environment=build_env,
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": PACKER_INSTALL},
                    "build": {
                        "commands": [
                            "packer build -var-file=packer/variables.pkrvars.hcl packer/base.pkr.hcl | tee /tmp/packer-base.log",
                            "AMI_ID=$(grep -oE '\\bami-[0-9a-f]+\\b' /tmp/packer-base.log | tail -1)",
                            "python scripts/publish_ami.py --ami-id $AMI_ID --type base",
                            "python scripts/verify_ami.py --type base",
                        ]
                    },
                },
            }),
        )

        codebuild.Project(
            self,
            "AppAMIBuild",
            project_name="ops-lab-build-app-ami",
            role=codebuild_role,
            environment=build_env,
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": PACKER_INSTALL},
                    "build": {
                        "commands": [
                            "packer build -var-file=packer/variables.pkrvars.hcl packer/app.pkr.hcl | tee /tmp/packer-app.log",
                            "AMI_ID=$(grep -oE '\\bami-[0-9a-f]+\\b' /tmp/packer-app.log | tail -1)",
                            "python scripts/publish_ami.py --ami-id $AMI_ID --type app",
                            "python scripts/verify_ami.py --type app",
                        ]
                    },
                },
            }),
        )
