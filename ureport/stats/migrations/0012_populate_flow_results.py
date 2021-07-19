# Generated by Django 2.2.20 on 2021-07-19 10:44

import time

from django.db import migrations

from ureport.utils import chunk_list


def noop(apps, schema_editor):  # pragma: no cover
    pass


def populate_flow_results(apps, schema_editor):  # pragma: no cover
    Org = apps.get_model("orgs", "Org")
    PollQuestion = apps.get_model("polls", "PollQuestion")
    PollResponseCategory = apps.get_model("polls", "PollResponseCategory")
    PollStats = apps.get_model("stats", "PollStats")

    assert not PollQuestion.objects.filter(flow_result=None).exists()
    assert not PollResponseCategory.objects.filter(flow_result_category=None).exists()

    start_time = time.time()
    orgs = Org.objects.all().order_by("id")
    count = 0
    total = PollStats.objects.all().count()

    for org in orgs:
        print(f"Migrating polls stats on org #{org.id}")
        poll_questions = PollQuestion.objects.filter(poll__org_id=org.id).select_related("flow_result")

        for poll_question in poll_questions:
            poll_stats_ids = PollStats.objects.filter(question_id=poll_question.id).only("id")

            for batch in chunk_list(poll_stats_ids, 1000):
                stats_batch = [elt.id for elt in list(batch)]
                updated = PollStats.objects.filter(pk__in=stats_batch).update(
                    flow_result_id=poll_question.flow_result_id
                )
                count += updated
                elapsed = time.time() - start_time
                print(f"Migrated flow_result for {count} of {total} poll stats in {elapsed:.1f} seconds")

            question_with_category_total = (
                PollStats.objects.filter(question_id=poll_question.id).exclude(category=None).count()
            )
            migrated_count = 0
            poll_response_categories = PollResponseCategory.objects.filter(question=poll_question)

            for poll_response_category in poll_response_categories:
                poll_stats_ids = PollStats.objects.filter(category_id=poll_response_category.id).only("id")

                for batch in chunk_list(poll_stats_ids, 1000):
                    stats_batch = [elt.id for elt in list(batch)]
                    updated = PollStats.objects.filter(pk__in=stats_batch).update(
                        flow_result_category_id=poll_response_category.flow_result_category_id
                    )
                    migrated_count += updated
                    elapsed = time.time() - start_time
                    print(
                        f"Migrated flow_result_category for {migrated_count} of {question_with_category_total} poll stats for quetion {poll_question.id} in {elapsed:.1f} seconds"
                    )

        print(f"Finished migrating polls stats on org #{org.id}")


def apply_manual():  # pragma: no cover
    from django.apps import apps

    populate_flow_results(apps, None)


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0011_auto_20210716_1854"),
    ]

    operations = [migrations.RunPython(populate_flow_results, noop)]
