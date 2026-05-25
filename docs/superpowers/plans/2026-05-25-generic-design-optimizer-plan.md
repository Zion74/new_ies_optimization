# Generic Design Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend GenericModelBuilder toward a real generic double-layer optimization backend with dynamic capacity variables.

**Architecture:** The outer layer uses `capacity_variables` generated from the generic component plan to build a variable-dimensional capacity search space. The inner layer will use GenericModelBuilder / GenericDispatchModel to evaluate each candidate capacity vector, eventually solving OEMOF/Pyomo dispatch for each candidate.

**Tech Stack:** Python, existing YAML scenario interface, GenericBackendPlanner, GenericModelBuilder, oemof.solph where available, current lightweight script-style tests.

---

## Phase 1: Dynamic Capacity Space

- Create `generic_capacity_space.py`.
- Convert `capacity_variables` into ordered optimization variables.
- Support any number of enabled devices.
- Export names, lower bounds, upper bounds, units, and vector-to-device-capacity mapping.

## Phase 2: Generic Dispatch Evaluation Interface

- Create `generic_dispatch_model.py`.
- Accept resolved scenario and capacity assignment.
- Build generic model components through `GenericModelBuilder`.
- Return an evaluation object with status, investment cost, build gaps, and future dispatch placeholders.

## Phase 3: Generic Design Optimizer

- Create `generic_design_optimizer.py`.
- Run a minimal variable-dimensional search for smoke tests.
- Keep the algorithm backend swappable so NSGA-II/DE can be introduced without rewriting the interface.

## Phase 4: CLI and Reports

- Add `--run-generic-design`.
- Export generic capacity solutions and reports.
- Make clear when the inner model is build-only versus dispatch-solved.

## Phase 5: Real OEMOF/Pyomo Dispatch Solver

- Replace build-only evaluation with real dispatch solve.
- Map each capacity variable into OEMOF nominal capacities.
- Compute annualized objective values.
- Connect to outer optimizer for real double-layer planning.

