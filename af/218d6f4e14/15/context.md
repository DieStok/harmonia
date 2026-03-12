# Session Context

## User Prompts

### Prompt 1

# Create a plan for a new feature or bug fix

## Introduction

**Note: The current year is 2026.** Use this when dating plans and searching for recent documentation.

Transform feature descriptions, bug reports, or improvement ideas into well-structured markdown files issues that follow project conventions and best practices. This command provides flexible detail levels to match your needs.

## Feature Description

<feature_description> #skill </feature_description>

**If the feature description...

### Prompt 2

dashboard comprehensive logging implementation. Should print to a subfolder dashboard in the logs folder. Also make a tab in the dashboard where I can see the whole log of all interactions I do and have done.

### Prompt 3

Base directory for this skill: /home/cog/dstoker/.claude/plugins/cache/compound-engineering-plugin/compound-engineering/2.38.1/skills/document-review

# Document Review

Improve brainstorm or plan documents through structured review.

## Step 1: Get the Document

**If a document path is provided:** Read it, then proceed to Step 2.

**If no document is specified:** Ask which document to review, or look for the most recent brainstorm/plan in `docs/brainstorms/` or `docs/plans/`.

## Step 2: Assess...

### Prompt 4

# Work Plan Execution Command

Execute a work plan efficiently while maintaining quality and finishing features.

## Introduction

This command takes a work document (plan, specification, or todo file) and executes it systematically. The focus is on **shipping complete features** by understanding requirements quickly, following existing patterns, and maintaining quality throughout.

## Input Document

<input_document> #docs/plans/2026-03-12-feat-dashboard-logging-and-trace-explorer-fixes-plan.md...

