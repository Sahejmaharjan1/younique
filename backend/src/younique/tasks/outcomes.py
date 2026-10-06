class BusinessFailure(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class InfrastructureFailure(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
