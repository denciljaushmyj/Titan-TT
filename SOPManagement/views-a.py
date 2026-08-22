import logging

from django.core.paginator import Paginator
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from adminportal.decorators import IsAdminPermission
from adminportal.services import is_admin_user

from . import selectors, services
from .serializers import (
    SOPMasterDetailSerializer,
    SOPMasterListSerializer,
    SOPModuleSerializer,
    SOPUpdateSerializer,
    SOPUploadSerializer,
)

logger = logging.getLogger(__name__)


class SOPManagementPageView(APIView):
    """
    SOP Management screen shell. Reachable by any authenticated user (same
    convention as AdminPortalView), but the template only renders the
    list/upload/edit UI when is_admin is True — otherwise it shows an
    access-restricted notice. All mutating admin/* APIs are independently
    enforced with IsAdminPermission regardless of what this page renders.
    """
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'SOPManagement/SOP_Management.html'

    def get(self, request):
        return Response({
            'is_admin': is_admin_user(request.user),
        })


class SOPModuleListAPIView(APIView):
    """GET /sop_management/api/sop/modules/ — module picker for the header SOP viewer."""
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        modules = selectors.get_active_sop_modules()
        return Response(SOPModuleSerializer(modules, many=True).data)


class SOPActiveByModuleAPIView(APIView):
    """GET /sop_management/api/sop/<module_id>/ — active SOP for the selected module."""
    http_method_names = ['get', 'head', 'options']

    def get(self, request, module_id):
        sop = selectors.get_active_sop_for_module(module_id)
        if sop is None:
            logger.info('[SOP_VIEW] module_id=%s user=%s result=NOT_UPLOADED', module_id, request.user)
            return Response({
                'found': False,
                'message': 'SOP not uploaded for this module.',
            }, status=200)

        logger.info('[SOP_VIEW] module_id=%s user=%s sop_id=%s', module_id, request.user, sop.id)
        data = SOPMasterDetailSerializer(sop, context={'request': request}).data
        return Response({'found': True, 'sop': data}, status=200)


class SOPAdminListAPIView(APIView):
    """GET /sop_management/api/admin/sop/list/ — paginated, searchable, filterable SOP list."""
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        search = request.GET.get('search', '').strip()
        module_id = request.GET.get('module_id') or None
        status = request.GET.get('status') or None
        page_size = min(int(request.GET.get('page_size', 10) or 10), 100)

        queryset = selectors.get_admin_sop_list(search=search, module_id=module_id, status=status)
        paginator = Paginator(queryset, page_size)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        return Response({
            'results': SOPMasterListSerializer(page_obj.object_list, many=True, context={'request': request}).data,
            'count': paginator.count,
            'num_pages': paginator.num_pages,
            'current_page': page_obj.number,
        })


class SOPUploadAPIView(APIView):
    """POST /sop_management/api/admin/sop/upload/ — create a new SOP version."""
    permission_classes = [IsAuthenticated, IsAdminPermission]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['post', 'options']

    def post(self, request):
        logger.info(
            '[SOP_UPLOAD] [INPUT] user=%s module=%s title=%s',
            request.user, request.data.get('module'), request.data.get('sop_title'),
        )
        serializer = SOPUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=400)

        validated = serializer.validated_data
        try:
            sop = services.create_sop(
                module_id=validated['module'].id,
                sop_title=validated['sop_title'],
                version=validated['version'],
                description=validated.get('description', ''),
                file_obj=validated['file'],
                is_active=validated.get('is_active', True),
                user=request.user,
            )
        except Exception:
            logger.exception('[SOP_UPLOAD] failed for user=%s', request.user)
            return Response({'error': 'Failed to upload SOP. Please try again.'}, status=500)

        return Response(
            SOPMasterListSerializer(sop, context={'request': request}).data, status=201
        )


class SOPUpdateAPIView(APIView):
    """PUT /sop_management/api/admin/sop/update/<id>/ — update an existing SOP."""
    permission_classes = [IsAuthenticated, IsAdminPermission]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['put', 'options']

    def put(self, request, pk):
        logger.info('[SOP_UPDATE_API] [INPUT] sop_id=%s user=%s', pk, request.user)
        existing = selectors.get_sop_by_id(pk)
        if existing is None:
            return Response({'error': 'SOP not found.'}, status=404)

        serializer = SOPUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=400)

        validated = serializer.validated_data
        try:
            sop = services.update_sop(
                sop_id=pk,
                user=request.user,
                sop_title=validated.get('sop_title'),
                version=validated.get('version'),
                description=validated.get('description'),
                file_obj=validated.get('file'),
                is_active=validated.get('is_active'),
            )
        except Exception:
            logger.exception('[SOP_UPDATE_API] failed for sop_id=%s', pk)
            return Response({'error': 'Failed to update SOP. Please try again.'}, status=500)

        if sop is None:
            return Response({'error': 'SOP not found.'}, status=404)

        return Response(SOPMasterListSerializer(sop, context={'request': request}).data)


class SOPDeleteAPIView(APIView):
    """DELETE /sop_management/api/admin/sop/delete/<id>/ — soft delete only."""
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['delete', 'options']

    def delete(self, request, pk):
        logger.info('[SOP_DELETE_API] [INPUT] sop_id=%s user=%s', pk, request.user)
        sop = services.soft_delete_sop(sop_id=pk, user=request.user)
        if sop is None:
            return Response({'error': 'SOP not found.'}, status=404)
        return Response({'success': True})
