#!/usr/bin/env python
"""
T12 상태 확인 스크립트

현재 threshold와 premise 상태를 요약해서 보여줍니다.
"""

from pathlib import Path
import yaml


def check_t12_status():
    """T12 작업 상태를 확인합니다."""

    # Load thresholds
    thresholds_path = Path("data/thresholds.yaml")
    with open(thresholds_path) as f:
        thresholds = yaml.safe_load(f)

    # Load premises
    premises_path = Path("data/premises.yaml")
    with open(premises_path) as f:
        premises = yaml.safe_load(f)

    print("\n" + "=" * 80)
    print("T12 Threshold Status Check")
    print("=" * 80 + "\n")

    # Count by status
    ready = []
    needs_buffer = []
    not_ready = []
    enabled = []

    for indicator_id, config in thresholds.items():
        has_anchor = config.get('anchor') is not None
        has_rationale = bool(config.get('anchor_rationale'))
        has_buffer = config.get('buffer') is not None
        is_enabled = config.get('enabled', False)

        if is_enabled:
            enabled.append(indicator_id)

        if has_anchor and has_rationale and has_buffer:
            ready.append(indicator_id)
        elif has_anchor and has_rationale and not has_buffer:
            needs_buffer.append(indicator_id)
        else:
            not_ready.append(indicator_id)

    # Print summary
    print(f"[TOTAL] Thresholds: {len(thresholds)}\n")

    print(f"[READY] {len(ready)} thresholds (have anchor + rationale + buffer)")
    for ind in ready:
        status = "[ENABLED]" if ind in enabled else "[disabled]"
        print(f"   - {ind:30s} {status}")

    print(f"\n[NEEDS BUFFER] {len(needs_buffer)} thresholds (need buffer derivation)")
    for ind in needs_buffer:
        print(f"   - {ind}")

    print(f"\n[NOT READY] {len(not_ready)} thresholds (incomplete)")
    for ind in not_ready:
        print(f"   - {ind}")

    # Check premises
    print("\n" + "-" * 80)
    print("Premise Status")
    print("-" * 80 + "\n")

    decidable_count = 0
    undecidable_count = 0
    no_indicator_count = 0

    for premise_id, config in premises.items():
        indicator_id = config.get('indicator_id')
        is_undecidable = config.get('undecidable', False)

        if is_undecidable:
            undecidable_count += 1
            print(f"[UNDECIDABLE] {premise_id}")
            rationale = config.get('undecidable_rationale', 'N/A')
            print(f"   Reason: {rationale}")
        elif indicator_id:
            decidable_count += 1
            # Check if threshold exists and is ready
            if indicator_id in ready:
                status = "[READY]"
            elif indicator_id in needs_buffer:
                status = "[NEEDS BUFFER]"
            elif indicator_id in not_ready:
                status = "[NOT READY]"
            else:
                status = "[UNKNOWN]"
            print(f"[DECIDABLE] {premise_id}: {indicator_id:30s} {status}")
        else:
            no_indicator_count += 1

    print(f"\nPremise Summary:")
    print(f"  - Decidable: {decidable_count}")
    print(f"  - Undecidable: {undecidable_count}")
    print(f"  - No indicator: {no_indicator_count}")

    # T12 checklist
    print("\n" + "=" * 80)
    print("T12 Completion Checklist")
    print("=" * 80 + "\n")

    checklist = [
        (len(needs_buffer) == 0, "All implemented indicators have buffers"),
        (False, "Dry-run backfill successful (manual check required)"),
        (len(enabled) >= 1, f"At least 1 threshold enabled (current: {len(enabled)})"),
        (False, "Real backfill performed (manual check required)"),
        (undecidable_count > 0, "Undecidable premises documented"),
    ]

    for completed, task in checklist:
        mark = "[X]" if completed else "[ ]"
        print(f"{mark} {task}")

    # Recommendations
    print("\n" + "=" * 80)
    print("Next Actions")
    print("=" * 80 + "\n")

    if needs_buffer:
        print("[1] Derive buffers:")
        for ind in needs_buffer:
            print(f"   bm thresholds derive {ind}")
        print()

    if ready and not enabled:
        print("[2] Dry-run backfill:")
        print("   bm backfill --from 2024-07-01")
        print()
        print("[3] Enable thresholds:")
        print("   Edit data/thresholds.yaml -> enabled: true")
        print()

    if enabled:
        print("[4] Perform real backfill:")
        print("   bm backfill --from 2024-07-01 --commit")
        print()
        print("[5] Check results:")
        print("   bm log --limit 20")
        print("   bm report")
        print()

    print("\n[GUIDE] See T12_CHECKLIST.md for detailed instructions\n")


if __name__ == "__main__":
    check_t12_status()
