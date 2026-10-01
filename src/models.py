from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class SubnetSpec:
    cidr_block: str
    availability_zone: str | None = None
    name: str | None = None
    public: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VpcSpec:
    name: str
    cidr_block: str
    subnets: list[SubnetSpec]
    region: str

    def has_public_subnets(self) -> bool:
        return any(s.public for s in self.subnets)


@dataclass
class CreatedSubnet:
    subnet_id: str
    cidr_block: str
    availability_zone: str
    name: str | None
    public: bool
    route_table_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
