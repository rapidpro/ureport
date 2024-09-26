import logging
import time
from abc import abstractmethod

from django.db import connection, models
from django.db.models import Sum


class SquashableModel(models.Model):
    """
    Base class for models which track counts by delta insertions which are then periodically squashed
    """

    squash_over = ()

    id = models.BigAutoField(auto_created=True, primary_key=True)
    is_squashed = models.BooleanField(default=False)

    @classmethod
    def get_unsquashed(cls):
        return cls.objects.filter(is_squashed=False)

    @classmethod
    def squash(cls):
        start = time.time()
        num_sets = 0

        for distinct_set in cls.get_unsquashed().order_by(*cls.squash_over).distinct(*cls.squash_over)[:5000]:
            with connection.cursor() as cursor:
                sql, params = cls.get_squash_query(distinct_set)

                cursor.execute(sql, params)

            num_sets += 1

        time_taken = time.time() - start

        logging.info("Squashed %d distinct sets of %s in %0.3fs" % (num_sets, cls.__name__, time_taken))

    @classmethod
    @abstractmethod
    def get_squash_query(cls, distinct_set) -> tuple:  # pragma: no cover
        pass

    @classmethod
    def sum(cls, instances) -> int:
        count_sum = instances.aggregate(count_sum=Sum("count"))["count_sum"]
        return count_sum if count_sum else 0

    class Meta:
        abstract = True
