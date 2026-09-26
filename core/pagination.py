from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


def build_paginated_response(data, paginate_info, message_code="search",
                             message_default="", message_details=""):
    return {
        "success": True,
        "message": {
            "code": message_code,
            "default": message_default,
            "details": message_details
        },
        "data": data,
        "paginate": paginate_info
    }


class CustomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(build_paginated_response(
            data=data,
            paginate_info={
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            message_code='list',
            message_default='Informations chargées',
            message_details=''
        ))

