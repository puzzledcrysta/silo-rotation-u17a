from app.evidence import distribution
from .versions import split_versions


def inspect(records, rejected):
    ready, duplicate, conflicts = split_versions(records)
    quarantine = sorted([*rejected,*conflicts],key=lambda row:row['line'])
    return {'ready':ready,'suppressed':sorted(duplicate,key=lambda row:row['line']),
            'rejected':quarantine,'reasons':distribution(quarantine)}
