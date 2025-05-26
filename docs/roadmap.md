# Reddit-TTS-Video

## 1. Project Vision & Goals

- What problem does the app solve?
    - Lack of diversity in the AI - generated reddit video space
- Who are the target users?
    - Viewers who already watch AI - generated content specifically. 
- What is the MVP (Minimum Viable Product)?
    - Grabbing a Reddit story and generating a short form of content accessible to users

## 2. Feature Brainstorm

- Core features (list ideas)
    Paste link from a Reddit URL and generate a video
    Connect to social media platforms such as YouTube, TikTok, Instagram to upload videos to
- Nice-to-have features
    LLM rating "new" posts and adding them to a queue for videos to be processed and uploaded to social media platforms.
- Stretch goals

## 3. Architecture & Tech Stack

- Major components/modules
    - AI generation software
    - Backend is in Python
- Libraries & frameworks to consider
    TBD
- Data storage (DB, files, etc.)
    TBD

## 4. Milestones & Timeline

- Phase 1: Initial setup & scaffolding
    - Webscrape reddit stories
    - Find library that can use tts 
    - Find library that can automate video editing
    - Build a end to end process to input webscraped reddit story into local storage
    - Generate background gameplay to use
- Phase 2: Upload to Social Media Platforms
    - Build an uploader that uploads local shorts to YouTube
- Phase 3: Integrate LLM to rate videos
    - Highly rated videos would be prioritized in uploading process in a queue
    - Train LLM to recognise "Best Post" of the day characteristics and properties to further improve rating efficacy. Could allow to webscrape by "new" posts
- Phase 4: Capture metadata about processes
    - Have LLMs store metrics about render time, memory usage to improve efficency in a database

## 5. Risks & Unknowns

- Technical challenges
    - Storing generated content
    - Finding the correct video-editing style
    - Knowledge about training a LLM
- Open questions
    - Where are we going to store generated content? 
    - What database will we use?