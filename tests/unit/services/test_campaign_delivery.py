from src.workers.queue import InMemoryJobQueue


def test_queue_returns_jobs_once_and_preserves_payload():
    queue = InMemoryJobQueue()
    first = queue.enqueue("campaign.deliver", {"campaign_id": "abc"})
    second = queue.enqueue("campaign.deliver", {"campaign_id": "def"})
    assert [job.id for job in queue.drain(1)] == [first.id]
    assert queue.drain()[0].id == second.id
    assert queue.drain() == []
