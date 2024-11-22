from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_autoscaling as autoscaling,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class TestStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for source code
        source_bucket = s3.Bucket(
            self,
            "SourceCodeBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy source code to S3
        s3deploy.BucketDeployment(
            self,
            "DeploySource",
            sources=[s3deploy.Source.asset("../src")],
            destination_bucket=source_bucket,
        )

        # Create VPC
        vpc = ec2.Vpc(
            self,
            "ECSClusterVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Create IAM role for EC2 instances
        instance_role = iam.Role(
            self,
            "ECSInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # Add S3 access to instance role
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[source_bucket.bucket_arn, f"{source_bucket.bucket_arn}/*"],
            )
        )

        # Create security group for ECS instances
        instance_sg = ec2.SecurityGroup(
            self,
            "ECSInstanceSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for ECS instances",
        )

        # Create ECS Cluster
        cluster = ecs.Cluster(
            self,
            "ECSCluster",
            vpc=vpc,
        )

        # User data for ECS instance to build and push container image
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "echo 'ECS_CLUSTER=" + cluster.cluster_name + "' >> /etc/ecs/ecs.config",
            "systemctl start ecs",
            "systemctl enable ecs",
        )

        # Create Launch Template
        launch_template = ec2.LaunchTemplate(
            self,
            "ECSLaunchTemplate",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.from_ssm_parameter(
                "/aws/service/ecs/optimized-ami/amazon-linux-2/ami-0015e288e8871864a",
                os=ec2.OperatingSystemType.LINUX,
            ),
            role=instance_role,
            security_group=instance_sg,
            user_data=user_data,
        )

        # Create Auto Scaling Group
        asg = autoscaling.AutoScalingGroup(
            self,
            "ECSASG",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            launch_template=launch_template,
            min_capacity=1,
            max_capacity=3,
            desired_capacity=2,
        )

        # Add ASG Capacity Provider
        capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            auto_scaling_group=asg,
            enable_managed_termination_protection=False,
        )
        cluster.add_asg_capacity_provider(capacity_provider)

        # Create Task Definition
        task_definition = ecs.Ec2TaskDefinition(
            self,
            "TaskDef",
            network_mode=ecs.NetworkMode.BRIDGE,
        )

        # Add container to task definition using locally built image
        container = task_definition.add_container(
            "BackendContainer",
            image=ecs.ContainerImage.from_registry("54hg0220/test-backend-api"),
            memory_limit_mib=512,
            cpu=256,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="BackendContainer"),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=80, host_port=80, protocol=ecs.Protocol.TCP)
        )

        # Create ECS Service
        service = ecs.Ec2Service(
            self,
            "BackendService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=2,
            min_healthy_percent=50,
            max_healthy_percent=200,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider=capacity_provider.capacity_provider_name,
                    weight=1,
                )
            ],
        )

        # Outputs
        CfnOutput(
            self,
            "ClusterName",
            value=cluster.cluster_name,
            description="Name of the ECS Cluster",
        )
        CfnOutput(
            self,
            "ServiceName",
            value=service.service_name,
            description="Name of the ECS Service",
        )
        CfnOutput(
            self,
            "SourceBucketName",
            value=source_bucket.bucket_name,
            description="Name of the S3 bucket containing source code",
        )
