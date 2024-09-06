from snowflake.snowpark import Session


def sql(sess: Session, table: str, create: str) -> str:
    df = sess.table("sch1.tb1").select("c1")

    return f"""\
{create} transient dynamic table {table}
    warehouse = adhoc
    target_lag = downstream
    initialize = on_schedule
as
{df.queries["queries"][0]}
;"""
