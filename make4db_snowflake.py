"make4db provider for Snowflake"

import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from functools import cache
from itertools import islice
from textwrap import dedent
from typing import Any, Callable, Iterable, NamedTuple, Self, TextIO, cast

from make4db.provider import DDL, DbAccess, DbProvider, Feature, SchObj
from sfconn import getsess, pytype
from sfconn.utils import add_conn_args
from snowflake.snowpark import Session
from yappt import indent, tabulate
from yappt.grid import AsciiBoxStyle

logger = logging.getLogger(__name__)

__version__ = "0.1.2"


class ObjInfo(NamedTuple):
    obj: SchObj
    kind: str
    args: str | None

    def __str__(self) -> str:
        if self.args is not None:
            args = "(" + self.args.split("(", 1)[1].rsplit(")", 1)[0] + ")" if "(" in self.args else ""
            return f"{self.obj}{args}"

        return str(self.obj)


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

    def py2sql(self, fn: Callable[[Session, str, bool], DDL], object: str, replace: bool) -> Iterable[str]:
        ddl = fn(self.sess, object, replace)
        if isinstance(ddl, str):
            yield ddl
        else:
            yield from ddl

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
        all_objs = set(objs)

        def obj_deps() -> Iterable[tuple[SchObj, SchObj]]:
            obj_lit = ",\n".join((f"('{o.sch.upper()}', '{o.obj.upper()}')" for o in all_objs))

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

        def stream_deps() -> Iterable[tuple[SchObj, SchObj]]:
            def parse_objname(t: str) -> tuple[str, str, str] | None:
                try:
                    db, sch, tb = t.split(".")
                    return (db, sch, tb)
                except ValueError:
                    return None

            with self.sess.connection.cursor() as csr:
                csr.execute("SHOW STREAMS IN DATABASE")
                name_xref = {d.name: e for e, d in enumerate(csr.description)}
                cols = [name_xref["database_name"], name_xref["schema_name"], name_xref["name"], name_xref["table_name"]]
                deps = ((r[cols[0]], SchObj(r[cols[1]], r[cols[2]]), r[cols[3]]) for r in cast(Iterable[list[str]], csr))
                for g_db, g_obj, d_name in deps:
                    if g_obj in all_objs and (d := parse_objname(d_name)) is not None and d[0] == g_db:
                        yield (g_obj, SchObj(d[1], d[2]))

        yield from obj_deps()
        yield from stream_deps()

    def drop_except(self, objs: set[SchObj]) -> Iterable[str]:
        def sch_objs(sch: str) -> list[ObjInfo]:
            def get_objs(kind: str):
                with self.sess.connection.cursor() as csr:
                    csr.execute(f"show terse {kind}s in schema {sch}")
                    return [ObjInfo(SchObj.make(sch, r[1]), kind, None) for r in csr]  # type: ignore

            def get_fn(kind: str):
                with self.sess.connection.cursor() as csr:
                    csr.execute(f"show user {kind}s in schema {sch}")
                    return [ObjInfo(SchObj.make(sch, r[1]), kind, r[8]) for r in csr]  # type: ignore

            return get_objs("table") + get_objs("view") + get_objs("stream") + get_fn("function") + get_fn("procedure")

        for sch in set(o.sch for o in objs):
            for oi in sch_objs(sch):
                if oi.obj not in objs:
                    yield f"drop {oi.kind} {oi}"


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
