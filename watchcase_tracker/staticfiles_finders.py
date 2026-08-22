from django.contrib.staticfiles.finders import AppDirectoriesFinder


class ExcludeDRFBootstrapFinder(AppDirectoriesFinder):
    EXCLUDED_FILES = {
        "rest_framework/js/bootstrap.min.js",
    }

    def find(self, path, find_all=False):
        normalized_path = path.replace("\\", "/")

        if normalized_path in self.EXCLUDED_FILES:
            return [] if find_all else None

        return super().find(path, find_all=find_all)

    def list(self, ignore_patterns):
        for path, storage in super().list(ignore_patterns):
            normalized_path = path.replace("\\", "/")

            if normalized_path in self.EXCLUDED_FILES:
                continue

            yield path, storage