# Review with a subagent command

## Situation
During concept development we go through multiple cirtical review phases with the context being present

## Complication
The context helps to resolve issus but as a "last check" we should review the files with the help of a subagent to simulate an agent without any prior context looking at the plan.
Why this is better than just launching a new message? The subagent "reports" into the agent with the context from building and discussing the concept. Hence a lot of the feedback can be discarded and only the real issues surface.

## Solution
1: create a command /mg:review-with-subagent which applies the md file in this path
