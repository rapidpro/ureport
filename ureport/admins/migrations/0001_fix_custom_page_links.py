import re
from collections import defaultdict

from django.db import migrations
from django.utils.text import slugify


def fix_custom_page_links(apps, schema_editor):  # pragma: no cover
    """
    Gives every custom page a link that is a non-empty slug, unique within its org, keeping valid links where possible
    """
    DashBlock = apps.get_model("dashblocks", "DashBlock")

    blocks = DashBlock.objects.filter(dashblock_type__slug="additional_menu").order_by("org_id", "-is_active", "id")

    used = defaultdict(set)
    to_fix = []
    for block in blocks:
        link = block.link or ""
        if re.fullmatch(r"[\w-]+", link) and link not in used[block.org_id]:
            used[block.org_id].add(link)
        else:
            to_fix.append(block)

    for block in to_fix:
        base = slugify(block.link or "", allow_unicode=True)[:240] or f"page-{block.id}"
        link = base
        suffix = 2
        while link in used[block.org_id]:
            link = f"{base}-{suffix}"
            suffix += 1

        used[block.org_id].add(link)
        block.link = link
        block.save(update_fields=("link",))


class Migration(migrations.Migration):
    dependencies = [
        ("dashblocks", "0015_normalize_dashblock_tags"),
    ]

    operations = [
        migrations.RunPython(fix_custom_page_links, migrations.RunPython.noop),
    ]
