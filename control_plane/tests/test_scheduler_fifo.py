from control_plane.kernelq.scheduler_fifo import FIFOScheduler, Job


def test_fifo_order_simple():
    q = FIFOScheduler()
    a = Job(job_id="A", created_at=1)
    b = Job(job_id="B", created_at=2)
    c = Job(job_id="C", created_at=3)
    q.enqueue(a)
    q.enqueue(b)
    q.enqueue(c)

    assert q.dequeue() == a
    assert q.dequeue() == b
    assert q.dequeue() == c
    assert q.dequeue() is None


def test_dequeue_from_empty_returns_none():
    q = FIFOScheduler()
    assert q.dequeue() is None
    assert q.peek() is None
    assert q.size() == 0


def test_peek_does_not_remove():
    q = FIFOScheduler()
    a = Job(job_id="A", created_at=1)
    b = Job(job_id="B", created_at=2)
    c = Job(job_id="C", created_at=3)
    q.enqueue(a)
    q.enqueue(b)
    q.enqueue(c)

    # Peek should show the first job...
    assert q.peek() == a
    # ...but not remove it.
    assert q.size() == 3
    assert q.dequeue() == a
    assert q.dequeue() == b
    assert q.dequeue() == c
    assert q.dequeue() is None


def test_size_changes_with_enqueue_and_dequeue():
    q = FIFOScheduler()
    a = Job(job_id="A", created_at=1)
    b = Job(job_id="B", created_at=2)
    c = Job(job_id="C", created_at=3)
    assert q.size() == 0
    q.enqueue(a)
    q.enqueue(b)
    q.enqueue(c)
    assert q.size() == 3
    q.dequeue()
    assert q.size() == 2
    q.dequeue()
    assert q.size() == 1
    q.dequeue()
    assert q.size() == 0

