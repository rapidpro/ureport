from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Manifest storage for collected static files (content-hashed names with precompressed .gz/.br variants) which
    tolerates stylesheets that reference files we don't ship (source maps and icon fonts of vendored CSS). Django's
    manifest storage fails collectstatic on those; here the reference is left as-is and only files that exist get
    hashed urls. Likewise a file missing from the manifest (e.g. before collectstatic has run, as in development
    and tests) resolves to its unhashed url rather than raising.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:  # raised when the referenced file doesn't exist
            return name
