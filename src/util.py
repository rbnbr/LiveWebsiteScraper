import os
import time
from datetime import datetime
from dateutil import parser
from dateutil.parser import ParserError


def get_env_non_empty(env_name: str, default) -> str:
    """
    Returns the os.getenv(env_name) result.
    If the result is "", returns default.

    Note: even if the env_name exists but its value is "", this returns default.
    Returns always a string except if string is "" and default is None
    :param env_name:
    :param default:
    :return:
    """
    res = os.getenv(env_name, default="")
    if res == "":
        if default is None:
            return None
        return str(default)
    else:
        return res


def tt(fn, repeat: int = 1, *args, **kwargs):
    """
    For benchmarking reasons.
    Returns the final result of fn plus some timings.
    :param fn: the function to be executed
    :param repeat: how often fn is called
    :param args: passed to fn
    :param kwargs: passed to fn
    :return:
    """
    assert repeat > 0, "repeat must be greater 0"
    tot_ns = 0
    elapsed_ns = 0
    for_ns = time.time_ns()
    res = None
    for i in range(repeat):
        t1 = time.time_ns()
        res = fn(*args, **kwargs)
        t2 = time.time_ns()
        elapsed_ns = t2 - t1
        tot_ns += elapsed_ns
    for_loop_ns = time.time_ns() - for_ns
    return res, {
        "for_loop": for_loop_ns,
        "took total": tot_ns,
        "avg": tot_ns / repeat,
        "last": elapsed_ns
    }


def parse_timestamp(timestamp: str) -> datetime:
    """
    Uses dateutil.parser to parse the timestamp.
    :param timestamp:
    :return:
    """
    try:
        return parser.parse(timestamp)
    except ParserError as _:
        timestamp += str(datetime.utcnow().year)
        return parser.parse(timestamp)
    except Exception as e:
        raise e


def read_file_content(path_to_file: str):
    with open(path_to_file, "rt") as f:
        return f.read()


def append_element_dict_to_list_dict(list_dict: dict, element_dict: dict):
    """
    Appends the elements of @element_dict to the lists in @list_dict.
    If the elements don't have a list in @list_dict, create one first.
    :param list_dict:
    :param element_dict:
    :return:
    """
    for element in element_dict:
        if element not in list_dict:
            list_dict[element] = list()

        list_dict[element].append(element_dict[element])


def make_do_in_interval_fn(fn: callable, interval_s: float, start_s: float = None):
    """
    Returns a function that if called with arguments, calls the provided callable @fn with those arguments only if the
     currently elapsed time since the last call (or @start) is bigger or equal the provided @interval.
    Otherwise, returns directly.
    :param fn: the function that is to be called
    :param interval_s: the time that has to be elapsed during calls
    :param start_s: the initial time
    :return: A wrapper function for @fn that if called triggers @fn only if @interval has passed since the last call.
    The wrapper function will return three values
        (was_executed: bool, next_execution_time_s: float, return_of_function: object).
    - was executed: True if the function was executed during this call, else False
    - next_execution_time_s: The time (like time.time() + remaining_wait_time) that has to be reached when this
        function can be executed again. This time does not consider the end of the function,
            but the moment it was called.
    - return_of_function: The return value of the executed function. None if it wasn't executed.
    """
    last_accessed_s = start_s

    def fn_(*args, **kwargs):
        """
        A wrapper for @fn.
        :param args: args to pass to @fn
        :param kwargs: **kwargs to pass to @fn
        :return: (True, return of fn(*args, **kwargs)) if enough time has elapsed, else (False, None).
        """
        nonlocal last_accessed_s
        now = time.time()
        elapsed = now - (last_accessed_s if last_accessed_s is not None else 0)
        t = interval_s - elapsed
        if t <= 0:
            last_accessed_s = now
            return True, now + interval_s, fn(*args, **kwargs)

        return False, now + t, None
    return fn_


def create_sql_batch_upsert_query(tablename: str, columns: list, conflict_columns: list,
                                  update_on_conflict_columns: list, amount_values: int = 1):
    """
    WARNING: This is (probably) not the recommended approach to build sql strings!
    :param tablename:
    :param columns:
    :param conflict_columns:
    :param update_on_conflict_columns:
    :param amount_values:
    :return:
    """
    assert len(columns) > 0, "provide columns"
    assert len(conflict_columns) > 0, "provide on conflict column(s)"
    cols = "".join([col + ", " for col in columns[:-1]])
    values = "".join(["%s, " for col in columns[:-1]])
    cols += columns[-1]
    values += "%s"
    multiple_values = "".join([f"({values}), " for i in range(amount_values - 1)])
    multiple_values += f"({values})"
    conflc = "".join([col + ", " for col in conflict_columns[:-1]])
    conflc += conflict_columns[-1]
    set_cols = ""
    excluded = ""
    for col in update_on_conflict_columns[:-1]:
        set_cols += col + ", "
        excluded += "EXCLUDED." + col + ", "
    if update_on_conflict_columns[-1]:
        set_cols += update_on_conflict_columns[-1]
        excluded += "EXCLUDED." + update_on_conflict_columns[-1]
    sql = f"""\
INSERT INTO {tablename} ({cols})
VALUES {multiple_values}
ON CONFLICT ({conflc}) DO UPDATE SET
({set_cols}) = ({excluded});"""
    return sql


def create_sql_batch_insert_query(tablename: str, columns: list, amount_values: int = 1,
                                  ignore_conflicts: bool = False):
    """
    WARNING: This is (probably) not the recommended approach to build sql strings!
    :param tablename:
    :param columns:
    :param amount_values:
    :param ignore_conflicts:
    :return:
    """
    assert len(columns) > 0, "provide columns"
    cols = "".join([col + ", " for col in columns[:-1]])
    values = "".join(["%s, " for col in columns[:-1]])
    cols += columns[-1]
    values += "%s"
    multiple_values = "".join([f"({values}), " for i in range(amount_values - 1)])
    multiple_values += f"({values})"

    if ignore_conflicts:
        on_conflict = """ ON CONFLICT DO NOTHING"""
    else:
        on_conflict = ""

    sql = f"""\
INSERT INTO {tablename} ({cols})
VALUES {multiple_values}
{on_conflict};"""
    return sql


def create_sql_batch_query(tablename: str, search_columns: list, equal_columns: list, amount_values: int = 1):
    """
    WARNING: This is (probably) not the recommended approach to build sql strings!
    :param tablename:
    :param search_columns:
    :param equal_columns:
    :param amount_values:
    :return:
    """
    scols = "".join([col + ", " for col in search_columns[:-1]])
    scols += search_columns[-1]

    ecols = "".join([col + ", " for col in equal_columns[:-1]])
    ecols += equal_columns[-1]

    values = "".join(["(%s), " for i in range(amount_values - 1)])
    values += "(%s)"
    sql = f"""\
SELECT {scols} FROM {tablename} WHERE ({ecols}) IN (VALUES {values});"""
    return sql
