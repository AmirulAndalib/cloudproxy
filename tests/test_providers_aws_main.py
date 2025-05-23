import pytest
from unittest.mock import patch, Mock
import datetime
from datetime import timezone
import time

from cloudproxy.providers.aws.main import (
    aws_deployment,
    aws_check_alive,
    aws_check_delete,
    aws_check_stop,
    aws_start
)
from cloudproxy.providers.settings import delete_queue, restart_queue, config

# Setup fixtures
@pytest.fixture
def setup_instances():
    """Setup test instances and restore original state after test"""
    # Save original values
    original_delete_queue = delete_queue.copy()
    original_restart_queue = restart_queue.copy()
    
    # Calculate a launch time that's just a few seconds ago to avoid age limit recycling
    just_now = datetime.datetime.now(timezone.utc)
    
    # Create test instances
    running_instance = {
        "Instances": [
            {
                "InstanceId": "i-12345",
                "PublicIpAddress": "1.2.3.4",
                "State": {
                    "Name": "running"
                },
                "LaunchTime": just_now  # Use a recent launch time
            }
        ]
    }
    
    stopped_instance = {
        "Instances": [
            {
                "InstanceId": "i-67890",
                "PublicIpAddress": "5.6.7.8",
                "State": {
                    "Name": "stopped"
                },
                "LaunchTime": just_now  # Use a recent launch time
            }
        ]
    }
    
    instances = [running_instance, stopped_instance]
    
    yield instances
    
    # Restore original state
    delete_queue.clear()
    delete_queue.update(original_delete_queue)
    restart_queue.clear()
    restart_queue.update(original_restart_queue)

@pytest.fixture
def test_instance_config():
    """Create a test instance configuration"""
    return {
        "enabled": True,
        "ips": [],
        "scaling": {"min_scaling": 2, "max_scaling": 5},
        "size": "t3.micro",
        "region": "us-west-2",
        "ami": "ami-test",
        "display_name": "Test Instance",
        "secrets": {
            "access_key_id": "test-access-key",
            "secret_access_key": "test-secret-key"
        },
        "spot": False
    }

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_scale_up(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances):
    """Test scaling up AWS instances"""
    # Setup - Only 2 instances, need to scale up to 4
    mock_list_instances.return_value = setup_instances
    mock_create_proxy.return_value = True
    
    # Execute
    min_scaling = 4
    result = aws_deployment(min_scaling)
    
    # Verify
    assert mock_create_proxy.call_count == 2  # Should create 2 new instances
    assert mock_delete_proxy.call_count == 0  # Should not delete any
    assert result == 2  # Returns number of instances after deployment

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_with_instance_config(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances, test_instance_config):
    """Test scaling up AWS instances with specific instance configuration"""
    # Setup - Only 2 instances, need to scale up to 4
    mock_list_instances.return_value = setup_instances
    mock_create_proxy.return_value = True
    
    # Execute
    min_scaling = 4
    result = aws_deployment(min_scaling, test_instance_config)
    
    # Verify
    assert mock_create_proxy.call_count == 2  # Should create 2 new instances
    
    # Check that create_proxy was called with the test_instance_config
    for call in mock_create_proxy.call_args_list:
        assert call[0][0] == test_instance_config
    
    # Check that list_instances was called with the test_instance_config
    mock_list_instances.assert_called_with(test_instance_config)
    
    assert mock_delete_proxy.call_count == 0  # Should not delete any
    assert result == 2  # Returns number of instances after deployment

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_scale_down(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances):
    """Test scaling down AWS instances"""
    # Setup - 2 instances, need to scale down to 1
    mock_list_instances.return_value = setup_instances
    mock_delete_proxy.return_value = True
    
    # Execute
    min_scaling = 1
    result = aws_deployment(min_scaling)
    
    # Verify
    assert mock_delete_proxy.call_count == 1  # Should delete 1 instance
    assert mock_create_proxy.call_count == 0  # Should not create any
    assert result == 2  # Returns number of instances after deployment

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_scale_down_with_instance_config(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances, test_instance_config):
    """Test scaling down AWS instances with specific instance configuration"""
    # Setup - 2 instances, need to scale down to 1
    mock_list_instances.return_value = setup_instances
    mock_delete_proxy.return_value = True
    
    # Execute
    min_scaling = 1
    result = aws_deployment(min_scaling, test_instance_config)
    
    # Verify
    assert mock_delete_proxy.call_count == 1  # Should delete 1 instance
    
    # Check that delete_proxy was called with the correct instance ID and config
    mock_delete_proxy.assert_called_once_with(
        setup_instances[0]["Instances"][0]["InstanceId"], 
        test_instance_config
    )
    
    assert mock_create_proxy.call_count == 0  # Should not create any
    assert result == 2  # Returns number of instances after deployment

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_no_change(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances):
    """Test when no scaling change is needed"""
    # Setup - 2 instances, need to keep 2
    mock_list_instances.return_value = setup_instances
    
    # Execute
    min_scaling = 2
    result = aws_deployment(min_scaling)
    
    # Verify
    assert mock_delete_proxy.call_count == 0  # Should not delete any
    assert mock_create_proxy.call_count == 0  # Should not create any
    assert result == 2  # Returns number of instances

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.create_proxy')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_deployment_no_change_with_instance_config(mock_delete_proxy, mock_create_proxy, mock_list_instances, setup_instances, test_instance_config):
    """Test when no scaling change is needed with specific instance configuration"""
    # Setup - 2 instances, need to keep 2
    mock_list_instances.return_value = setup_instances
    
    # Execute with instance config
    min_scaling = 2
    result = aws_deployment(min_scaling, test_instance_config)
    
    # Verify
    assert mock_delete_proxy.call_count == 0  # Should not delete any
    assert mock_create_proxy.call_count == 0  # Should not create any
    
    # Check that list_instances was called with the test_instance_config
    mock_list_instances.assert_called_with(test_instance_config)
    
    assert result == 2  # Returns number of instances

def test_aws_check_alive_running_directly():
    """Test the aws_check_alive function directly with real function execution"""
    # This is a direct test that actually calls the real function,
    # but intercepts calls to dependencies with mocks
    with patch('cloudproxy.providers.aws.main.list_instances') as mock_list_instances:
        with patch('cloudproxy.providers.aws.main.check_alive') as mock_check_alive:
            with patch('cloudproxy.providers.aws.main.delete_proxy') as mock_delete_proxy:
                with patch('cloudproxy.providers.aws.main.start_proxy') as mock_start_proxy:
                    # Setup mocks
                    recent_time = datetime.datetime.now(timezone.utc)
                    mock_list_instances.return_value = [{
                        "Instances": [{
                            "InstanceId": "i-12345",
                            "PublicIpAddress": "1.2.3.4",
                            "State": {"Name": "running"},
                            "LaunchTime": recent_time
                        }]
                    }]
                    mock_check_alive.return_value = True
                    
                    # Execute
                    result = aws_check_alive()
                    
                    # Verify
                    assert "1.2.3.4" in result
                    assert mock_delete_proxy.call_count == 0  # Shouldn't delete recent instances
                    assert mock_start_proxy.call_count == 0  # Shouldn't start running instances

@patch('cloudproxy.providers.aws.main.check_alive')
@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.delete_proxy')
@patch('cloudproxy.providers.aws.main.start_proxy')
def test_aws_check_alive_with_instance_config(mock_start_proxy, mock_delete_proxy, mock_list_instances, 
                                             mock_check_alive, setup_instances, test_instance_config):
    """Test checking alive for instances with specific instance configuration"""
    # Setup
    mock_list_instances.return_value = setup_instances
    mock_check_alive.return_value = True
    
    # Execute with instance config
    result = aws_check_alive(test_instance_config)
    
    # Verify
    mock_list_instances.assert_called_once_with(test_instance_config)
    assert "1.2.3.4" in result  # IP from running instance should be in result
    
    # For stopped instance, start_proxy should be called
    mock_start_proxy.assert_called_once_with(
        setup_instances[1]["Instances"][0]["InstanceId"], 
        test_instance_config
    )

@patch('cloudproxy.providers.aws.main.check_alive')
@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.delete_proxy')
@patch('cloudproxy.providers.aws.main.start_proxy')
def test_aws_check_alive_stopped(mock_start_proxy, mock_delete_proxy, mock_list_instances, mock_check_alive, setup_instances):
    """Test checking alive for stopped instances"""
    # Setup
    mock_list_instances.return_value = [setup_instances[1]]  # Just the stopped instance
    mock_start_proxy.return_value = True
    mock_check_alive.return_value = False  # Instance not reachable yet since we just started it
    
    # Execute
    result = aws_check_alive()
    
    # Verify
    mock_start_proxy.call_count == 1  # Should start the stopped instance
    assert mock_delete_proxy.call_count == 0  # Should not delete any
    assert len(result) == 0  # No IPs ready yet as instance was just started

def test_aws_check_alive_age_limit_exceeded_directly():
    """Test the aws_check_alive function directly with simulated old instance"""
    # Save original age limit value
    original_age_limit = config["age_limit"]
    
    try:
        # Set age limit to a small value to make instances expire quickly
        config["age_limit"] = 60  # 60 seconds
        
        # Create a mock instance with a launch time far in the past
        with patch('cloudproxy.providers.aws.main.list_instances') as mock_list_instances:
            with patch('cloudproxy.providers.aws.main.check_alive') as mock_check_alive:
                with patch('cloudproxy.providers.aws.main.delete_proxy') as mock_delete_proxy:
                    with patch('cloudproxy.providers.aws.main.start_proxy') as mock_start_proxy:
                        # Setup mocks with an old instance (from year 2000)
                        very_old_time = datetime.datetime(2000, 1, 1, tzinfo=timezone.utc)
                        mock_list_instances.return_value = [{
                            "Instances": [{
                                "InstanceId": "i-12345", 
                                "PublicIpAddress": "1.2.3.4",
                                "State": {"Name": "running"},
                                "LaunchTime": very_old_time
                            }]
                        }]
                        mock_check_alive.return_value = True
                        mock_delete_proxy.return_value = True
                        
                        # Execute
                        result = aws_check_alive()
                        
                        # Verify
                        assert mock_delete_proxy.call_count == 1  # Should delete the expired instance
                        assert len(result) == 0  # No IPs in result as the instance was deleted
    finally:
        # Restore original age limit
        config["age_limit"] = original_age_limit

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_check_delete(mock_delete_proxy, mock_list_instances, setup_instances):
    """Test checking for instances to delete"""
    # Setup
    mock_list_instances.return_value = setup_instances
    mock_delete_proxy.return_value = True
    delete_queue.add("1.2.3.4")  # Add IP to delete queue
    
    # Execute
    aws_check_delete()
    
    # Verify
    assert mock_delete_proxy.call_count == 1  # Should delete the instance in delete queue
    assert "1.2.3.4" not in delete_queue  # IP should be removed from queue

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.delete_proxy')
def test_aws_check_delete_with_instance_config(mock_delete_proxy, mock_list_instances, setup_instances, test_instance_config):
    """Test checking for instances to delete with specific instance configuration"""
    # Setup
    mock_list_instances.return_value = setup_instances
    mock_delete_proxy.return_value = True
    delete_queue.add("1.2.3.4")  # Add IP to delete queue
    
    # Execute with instance config
    aws_check_delete(test_instance_config)
    
    # Verify
    mock_list_instances.assert_called_once_with(test_instance_config)
    
    # Should delete the instance with the instance config
    mock_delete_proxy.assert_called_once_with(
        setup_instances[0]["Instances"][0]["InstanceId"], 
        test_instance_config
    )
    
    assert "1.2.3.4" not in delete_queue  # IP should be removed from queue

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.stop_proxy')
def test_aws_check_stop(mock_stop_proxy, mock_list_instances, setup_instances):
    """Test checking for instances to stop"""
    # Setup
    mock_list_instances.return_value = [setup_instances[0]]  # Just the running instance
    mock_stop_proxy.return_value = True
    restart_queue.add("1.2.3.4")  # Add IP to restart queue
    
    # Execute
    aws_check_stop()
    
    # Verify
    assert mock_stop_proxy.call_count == 1  # Should stop the instance in restart queue

@patch('cloudproxy.providers.aws.main.list_instances')
@patch('cloudproxy.providers.aws.main.stop_proxy')
def test_aws_check_stop_with_instance_config(mock_stop_proxy, mock_list_instances, setup_instances, test_instance_config):
    """Test checking for instances to stop with specific instance configuration"""
    # Setup
    mock_list_instances.return_value = [setup_instances[0]]  # Just the running instance
    mock_stop_proxy.return_value = True
    restart_queue.add("1.2.3.4")  # Add IP to restart queue
    
    # Execute with instance config
    aws_check_stop(test_instance_config)
    
    # Verify
    mock_list_instances.assert_called_once_with(test_instance_config)
    
    # Should stop the instance with the instance config
    mock_stop_proxy.assert_called_once_with(
        setup_instances[0]["Instances"][0]["InstanceId"], 
        test_instance_config
    )
    
    assert "1.2.3.4" not in restart_queue  # IP should be removed from queue

@patch('cloudproxy.providers.aws.main.aws_check_delete')
@patch('cloudproxy.providers.aws.main.aws_check_stop')
@patch('cloudproxy.providers.aws.main.aws_check_alive')
@patch('cloudproxy.providers.aws.main.aws_deployment')
def test_aws_start(mock_aws_deployment, mock_aws_check_alive, mock_aws_check_stop, mock_aws_check_delete):
    """Test the main aws_start function"""
    # Setup
    mock_aws_check_alive.return_value = ["1.2.3.4", "5.6.7.8"]
    original_min_scaling = config["providers"]["aws"]["instances"]["default"]["scaling"]["min_scaling"]
    
    try:
        # Set test scaling
        config["providers"]["aws"]["instances"]["default"]["scaling"]["min_scaling"] = 3
        
        # Execute
        result = aws_start()
        
        # Verify
        mock_aws_check_delete.assert_called_once()
        mock_aws_check_stop.assert_called_once()
        # aws_check_alive is only called once in aws_start
        mock_aws_check_alive.assert_called_once()
        
        # Check deployment was called with the correct min_scaling from the instance config and the instance config itself
        default_config = config["providers"]["aws"]["instances"]["default"]
        mock_aws_deployment.assert_called_once_with(3, default_config)
        
        assert result == ["1.2.3.4", "5.6.7.8"]  # Should return IPs from check_alive
    finally:
        # Restore setting
        config["providers"]["aws"]["instances"]["default"]["scaling"]["min_scaling"] = original_min_scaling

@patch('cloudproxy.providers.aws.main.aws_check_delete')
@patch('cloudproxy.providers.aws.main.aws_check_stop')
@patch('cloudproxy.providers.aws.main.aws_check_alive')
@patch('cloudproxy.providers.aws.main.aws_deployment')
def test_aws_start_with_instance_config(mock_aws_deployment, mock_aws_check_alive, 
                                        mock_aws_check_stop, mock_aws_check_delete, test_instance_config):
    """Test the main aws_start function with specific instance configuration"""
    # Setup
    mock_aws_check_alive.return_value = ["1.2.3.4", "5.6.7.8"]
    
    # Execute with instance config
    result = aws_start(test_instance_config)
    
    # Verify all methods were called with the instance config
    mock_aws_check_delete.assert_called_once_with(test_instance_config)
    mock_aws_check_stop.assert_called_once_with(test_instance_config)
    mock_aws_check_alive.assert_called_once_with(test_instance_config)
    
    # Check deployment was called with the correct min_scaling from the instance config
    mock_aws_deployment.assert_called_once_with(
        test_instance_config["scaling"]["min_scaling"],
        test_instance_config
    )
    
    assert result == ["1.2.3.4", "5.6.7.8"]  # Should return IPs from check_alive 