from core.helpers import total_seconds, sum
from core.eventing import EventManager
from core.logger import Logger
from datetime import datetime
from sync.sync_task import SyncTaskStatistics

log = Logger('sync.sync_statistics')


class SyncStatistics(object):
    def __init__(self, handlers, manager):
        self.manager = manager

        self.key = None

        self.offset = None
        self.start = None
        self.end = None

        for h in handlers:
            self.bind(h)

    def bind(self, task):
        key = task.get_key()

        EventManager.subscribe(
            'sync.%s.started' % key,
            lambda start, end: self.started(key, start, end)
        )

        EventManager.subscribe(
            'sync.%s.progress' % key,
            lambda value: self.progress(key, value)
        )

        EventManager.subscribe(
            'sync.%s.finished' % key,
            lambda: self.finished(key)
        )

        # Bind child progress events
        for child in task.children:
            self.bind(child)

    def reset(self):
        self.manager.current.statistics = SyncTaskStatistics()

        self.key = None

        self.offset = None

        self.start = None
        self.end = None

    def started(self, key, start, end):
        log.debug('SyncStatistics.start(%s, %s, %s)', repr(key), start, end)
        self.reset()

        self.key = key

        self.offset = 0 - start

        self.start = start + self.offset
        self.end = end + self.offset

    def progress(self, key, value):
        log.debug('SyncStatistics.update(%s, %s)', repr(key), value)

        if key != self.key:
            log.warn('Invalid state (key: "%s" != "%s")', key, self.key)
            return

        value += self.offset

        stat = self.manager.current.statistics

        progress = float(value) / self.end

        self.calculate_timing(stat, progress)

        log.debug(
            '[%s] progress: %02d%%, estimated time remaining: ~%s seconds',
            key, progress * 100,
            round(stat.seconds_remaining, 2) if stat.seconds_remaining else '?'
        )

        stat.progress = progress
        stat.last_update = datetime.utcnow()

    def calculate_timing(self, stat, cur_progress):
        if not stat.last_update:
            return

        progress_delta = cur_progress - (stat.progress or 0)
        delta_seconds = total_seconds(datetime.utcnow() - stat.last_update)

        # Plot current percent/sec
        stat.plots.append(delta_seconds / (progress_delta * 100))

        # Calculate average percent/sec
        stat.per_perc = sum(stat.plots) / len(stat.plots)

        # Calculate estimated time remaining
        stat.seconds_remaining = ((1 - cur_progress) * 100) * stat.per_perc

        log.debug('plots: %s, per_perc: %s', stat.plots, stat.per_perc)



    def finished(self, key):
        log.debug('SyncStatistics.finish(%s)', repr(key))
        self.reset()
