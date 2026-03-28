from django.urls import reverse


def build_branding_asset_url(organization, variant: str, request=None) -> str | None:
    if not organization:
        return None
    slug = getattr(organization, "slug", None)
    if not slug:
        return None
    relative_url = reverse(
        "parties:organization-branding-logo-public",
        kwargs={"organization_slug": slug, "variant": variant},
    )
    return request.build_absolute_uri(relative_url) if request is not None else relative_url


def build_public_branding_logo_url(branding, variant: str, request=None) -> str | None:
    if not branding or not getattr(branding, "is_active", False):
        return None

    if variant == "small":
        logo_field = getattr(branding, "logo_small", None)
    elif variant == "primary":
        logo_field = getattr(branding, "logo_primary", None)
    else:
        return None

    if not logo_field:
        return None

    return build_branding_asset_url(getattr(branding, "organization", None), variant, request=request)
