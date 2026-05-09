from benchmark_precision import benchmark_precision
from benchmark_throughput import benchmark_throughput
import json


def format_precision_report(report_data):
    report = {
        "total_calls": f"{report_data['total_calls']}",
        "rate": f"{report_data['rate']}",
        "mode": report_data['mode'],
        "expected_time": f"{report_data['expected_total_time']}",
        "elapsed_time": f"{report_data['elapsed']:.6f}",
        "max_single_drift": f"{report_data['max_single_drift']:.6f}",
        "accuracy_pct": f"{report_data['accuracy_pct']:.2f}",
        "time_error": f"{report_data['time_error']:.6f}",
    }
    return report


def run_precision_report():
    reports = []
    rates = [5000, 10000, 20000, 50000, 100000, 200000]
    for rate in rates:
        total_calls = rate * 4
        period = 1
        burst_mode = True
        # print(f"--- {rate:,} calls/sec ({total_calls:,} calls with burst+mode={burst_mode})---) ---")
        r = benchmark_precision(rate,period, total_calls, burst_mode)
        reports.append(r)
    return reports

def generate_markdown_precision(reports):
    markdown = """# Benchmarks for Precision\n"""
    """This is a report for the precision benchmarks.\n"""
    report_list = [format_precision_report(r) for r in reports]
    columns: dict[str, int] = {}
    def get_max_lenths(r):
        for rr in r:
            for k, v in rr.items():
                columns[k] = max(columns.get(k, 0), len(str(v)), len(str(k)))
        return columns

    # create table header
    columns = get_max_lenths(report_list)
    markdown += "| " + " | ".join([f"{k:<{v}}" for k, v in columns.items()]) + " |\n"
    markdown += "| " + " | ".join(["-" * v for v in columns.values()]) + " |\n"

    for report in report_list:
        # create table body
        row = [f"{report[k]:<{v}}" for k, v in columns.items()]
        markdown += "| " + " | ".join(row) + " |"

        markdown += "\n"
    markdown += "\n"
    markdown += "> all values for durations are in seconds\n"
    return markdown


def export_report_precision(reports, report_name):

    with open(f'results/{report_name}.md', 'w') as f:
        md_text = generate_markdown_precision(reports)
        f.write(md_text)

    with open(f'results/{report_name}.json', 'w') as f:
        json.dump(reports, f, indent=2)


reports = run_precision_report()

report_name = "precision_benchmarks"

export_report_precision(reports, report_name)

def run_throughput_report():
    report_list = benchmark_throughput()
    return report_list

def generate_markdown_throughput(reports):
    markdown = """# Benchmarks for Throughput\n"""
    """This is a report for the throughput benchmarks.\n"""
    columns: dict[str, int] = {}
    def get_max_lenths(r):
        for rr in r:
            for k, v in rr.items():
                columns[k] = max(columns.get(k, 0), len(str(v)), len(str(k)))
        return columns

    # create table header
    columns = get_max_lenths(reports)
    markdown += "| " + " | ".join([f"{k:<{v}}" for k, v in columns.items()]) + " |\n"
    markdown += "| " + " | ".join(["-" * v for v in columns.values()]) + " |\n"

    for report in reports:
        # create table body
        row = [f"{report[k]:<{v}}" for k, v in columns.items()]
        markdown += "| " + " | ".join(row) + " |"

        markdown += "\n"
    markdown += "\n"
    markdown += "> all values for durations are in seconds\n"
    return markdown

def export_report_throughput(reports, report_name):

    with open(f'results/{report_name}.md', 'w') as f:
        md_text = generate_markdown_throughput(reports)
        f.write(md_text)

    with open(f'results/{report_name}.json', 'w') as f:
        json.dump(reports, f, indent=2)

reports = run_throughput_report()

report_name = "throughput_benchmarks"

export_report_throughput(reports, report_name)