"Snowflake provider for make4db"

import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from functools import cache
from itertools import islice
from textwrap import dedent
from typing import Any, Iterable, Self, TextIO, cast

from make4db.provider import DbAccess, DbProvider, Feature, PySqlFn, SchObj
from sfconn import getsess, pytype
from sfconn.utils import add_conn_args
from snowflake.snowpark import Session
from yappt import indent, tabulate
from yappt.grid import AsciiBoxStyle

logger = logging.getLogger(__name__)

__version__ = "0.1.0"


@dataclass
class SfAcc(DbAccess):
    conn_args: dict[str, Any]
    _sess: Session | None = None

    @property
    def sess(self) -> Session:
        if self._sess is None:
            self._sess = getsess(**self.conn_args)
        return self._sess

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        if self._sess is not None:
            self._sess.close()

    def py2sql(self, fn: PySqlFn, object: str, replace: bool) -> Iterable[str]:
        yield from fn(self.sess, object, replace)

    def execsql(self, sql: str, output: TextIO) -> None:
        with self.sess.connection.cursor() as csr:
            csr.execute(sql)
            tabulate(
                islice(cast(Iterable[tuple[Any, ...]], csr), 500),
                headers=[d.name for d in csr.description],
                types=[pytype(d) for d in csr.description],
                default_grid_style=AsciiBoxStyle,
                file=output,
            )

    def iterdep(self, objs: Iterable[SchObj]) -> Iterable[tuple[SchObj, SchObj]]:
        obj_lit = ",\n".join((f"('{o.sch.upper()}', '{o.obj.upper()}')" for o in objs))

        sql = dedent(
            f"""\
            with objs(sch_name, obj_name) as (
                select *
                from values {indent(obj_lit, 4)}
            )
            select distinct referencing_schema, referencing_object_name, referenced_schema, referenced_object_name
            from snowflake.account_usage.object_dependencies d
            join objs o on referencing_database = current_database()
                and referenced_database = current_database()
                and referencing_schema = o.sch_name
                and referencing_object_name = o.obj_name"""
        )

        with self.sess.connection.cursor() as csr:
            csr.execute(sql)
            yield from ((SchObj(r[0], r[1]), SchObj(r[2], r[3])) for r in cast(Iterable[tuple[str, str, str, str]], csr))


@dataclass
class SfProvider(DbProvider):
    def dbacc(self, conn_args: dict[str, Any]) -> SfAcc:
        return SfAcc(conn_args)

    def add_db_args(self, parser: ArgumentParser) -> None:
        add_conn_args(parser)

    def name(self) -> str:
        return "snowflake"

    def version(self) -> str:
        return __version__

    def supports_feature(self, feature: Feature) -> bool:
        return True


@cache
def get_provider() -> DbProvider:
    return SfProvider()
