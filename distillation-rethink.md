I want to rethink the tag distillation process first explored in plan-tag-distillation.md. The "Features Enabled by Distillation" section
still applies, but there are almost 30000 unclassified tags, which is too much for small chunks of manual categorization 
or approval as specified in the original plan.

i want to iterate on a process which will reduce the user interaction for bulk categorization to a minimum. I do want the user to
be able to do small category modification as necessary, but that would be more on a video by video case.

I like the original additive approach, so if that works with the improved process we come up with, let's keep that. And 
evaluate other pieces of the existing design worth keeping.

The previous non-llm approaches: Edit distance (Levenshtein), Token overlap, and Prefix, 
did not provide good results in practice with the actual video tags, so I want to continue to refine the llm approach.

We can make copies of the existing database to iterate on the new approach. 

for now we can ignore any existing manual categorization done by the user, as if we're starting the categorization process 
from scratch, given just the original ingested videos and associated youtube-sourced tags.

In the end, I want to be able to 
* distill the list of tags provided by the video publisher down to a canonical concept tag (like our original approach)
* limit low value publisher-provided tags (e.g. 2024, HD, #ad)
* limit tags that can apply too widely (e.g Home & Style)
* filter by canonical tag
* add a new tag to an individual video
* see pills of associated canonical tags on the video card
* apply the same canonical tag to multiple videos
* add/remove the non-canonical tags associated with a canonical tag 

Would it be a good idea to start a separate tag management project/subproject (webapp/ui and database) that focuses on a tight 
feedback loop to get the categorization process down well, before incorporating the improved process into the main web app?

How's our context doing. Should I start a clean session for the categorization rework?  

Ask me any refining questions as necessary. 



