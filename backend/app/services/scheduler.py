"""Single-process course-fair scheduler for recording and document processing."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from collections.abc import Awaitable, Callable


@dataclass
class Job:
    id: str
    course_id: str
    run: Callable[[], Awaitable[None]]
    done: Callable[[], None]


class CourseScheduler:
    def __init__(self, settings):
        self.limit = settings.job_concurrency
        self.course_limit = settings.course_job_concurrency
        self.queues: dict[str, deque[Job]] = {}
        self.order = deque()
        self.jobs: dict[str, Job] = {}
        self.active: dict[str, asyncio.Task] = {}
        self.running = False

    async def start(self):
        self.running = True
        self._dispatch()

    def submit(self, id, course_id, run, done):
        if id in self.jobs:
            raise ValueError("Source is already processing")
        job = Job(id, course_id, run, done)
        self.jobs[id] = job
        if course_id not in self.queues:
            self.queues[course_id] = deque()
            self.order.append(course_id)
        self.queues[course_id].append(job)
        self._dispatch()

    def _dispatch(self):
        if not self.running:
            return
        remaining = len(self.order)
        while len(self.active) < self.limit and remaining:
            course = self.order.popleft()
            self.order.append(course)
            count = sum(self.jobs[id].course_id == course for id in self.active)
            queue = self.queues[course]
            if queue and count < self.course_limit:
                job = queue.popleft()
                task = asyncio.create_task(job.run(), name=f"source-{job.id}")
                self.active[job.id] = task
                task.add_done_callback(lambda task, job=job: self._finished(job, task))
                remaining = len(self.order)
            else:
                remaining -= 1

    def _finished(self, job, task=None):
        if task is not None and not task.cancelled():
            # Processor runners persist failures; consume any unexpected exception.
            task.exception()
        self.active.pop(job.id, None)
        self.jobs.pop(job.id, None)
        job.done()
        if not self.queues[job.course_id] and not any(
            j.course_id == job.course_id for j in self.jobs.values()
        ):
            del self.queues[job.course_id]
            self.order.remove(job.course_id)
        self._dispatch()

    async def cancel(self, id):
        job = self.jobs.get(id)
        if not job:
            return
        if task := self.active.get(id):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            self.queues[job.course_id].remove(job)
            self._finished(job)

    async def stop(self):
        self.running = False
        for id in list(self.jobs):
            await self.cancel(id)
