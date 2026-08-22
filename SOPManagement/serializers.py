from django.urls import reverse
from rest_framework import serializers

from .models import SOPMaster, SOPModule
from .validators import validate_sop_file


class SOPModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SOPModule
        fields = ['id', 'name', 'sort_order', 'is_active']


class SOPMasterListSerializer(serializers.ModelSerializer):
    """Row shape for the admin SOP list table."""
    module_name = serializers.CharField(source='module.name', read_only=True)
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True, default='')
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = SOPMaster
        fields = [
            'id', 'module', 'module_name', 'sop_title', 'version', 'description',
            'file_url', 'file_name', 'file_size', 'uploaded_by_username',
            'uploaded_date', 'updated_at', 'is_active',
        ]

    def get_file_url(self, obj):
        """
        Relative URL to the authenticated SOP file-serve endpoint.

        Returns a same-origin relative path (not an absolute MEDIA_URL) so the
        browser resolves it against the current host — the raw /media/ path is
        not routed under the IIS production deployment (DEBUG/runserver only),
        which caused the "connection refused" error when opening the link.
        """
        if not obj.file:
            return None
        return reverse('sop_management:sop_file_serve', kwargs={'pk': obj.pk})


class SOPMasterDetailSerializer(SOPMasterListSerializer):
    """Payload returned for the user-facing "active SOP for module" endpoint."""

    class Meta(SOPMasterListSerializer.Meta):
        fields = SOPMasterListSerializer.Meta.fields + ['remarks']


class SOPUploadSerializer(serializers.Serializer):
    module = serializers.PrimaryKeyRelatedField(queryset=SOPModule.objects.all())
    sop_title = serializers.CharField(max_length=200)
    version = serializers.CharField(max_length=20)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    file = serializers.FileField()
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_file(self, value):
        error = validate_sop_file(value)
        if error:
            raise serializers.ValidationError(error)
        return value

    def validate_sop_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('SOP title is required.')
        return value

    def validate_version(self, value):
        if not value.strip():
            raise serializers.ValidationError('Version is required.')
        return value


class SOPUpdateSerializer(serializers.Serializer):
    sop_title = serializers.CharField(max_length=200, required=False)
    version = serializers.CharField(max_length=20, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_file(self, value):
        error = validate_sop_file(value)
        if error:
            raise serializers.ValidationError(error)
        return value

    def validate_sop_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('SOP title cannot be blank.')
        return value

    def validate_version(self, value):
        if not value.strip():
            raise serializers.ValidationError('Version cannot be blank.')
        return value
