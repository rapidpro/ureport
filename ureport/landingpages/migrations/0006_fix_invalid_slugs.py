import re

from django.db import migrations
from django.utils.text import slugify


def noop(apps, schema_editor):  # pragma: no cover
    pass


def fix_invalid_slugs(apps, schema_editor):  # pragma: no cover
    LandingPage = apps.get_model("landingpages", "LandingPage")

    # slugs saved before they were validated may not match the public URL pattern, which breaks reversing them
    for page in LandingPage.objects.all().order_by("id"):
        if re.fullmatch(r"[\w-]+", page.slug):
            continue

        base = slugify(page.slug, allow_unicode=True)[:120].strip("-") or f"page-{page.id}"
        taken = set(LandingPage.objects.filter(org_id=page.org_id).exclude(id=page.id).values_list("slug", flat=True))

        slug, count = base, 2
        while slug in taken:
            slug = f"{base}-{count}"
            count += 1

        print(f"Changing slug of landing page #{page.id} from '{page.slug}' to '{slug}'")
        page.slug = slug
        page.save(update_fields=("slug",))


class Migration(migrations.Migration):

    dependencies = [
        ("landingpages", "0005_alter_landingpage_unique_together_and_more"),
    ]

    operations = [migrations.RunPython(fix_invalid_slugs, noop)]
