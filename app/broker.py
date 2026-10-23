import json
import os


def publish_run_event(event: dict) -> bool:
    servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if not servers:
        return False
    try:
        from confluent_kafka import Producer
        producer = Producer({"bootstrap.servers": servers})
        producer.produce(os.getenv("WORKFLOW_TOPIC", "workflow-runs"), json.dumps(event).encode())
        producer.flush(5)
        return True
    except (ImportError, BufferError, RuntimeError):
        return False
