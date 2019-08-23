BASE_URL = "https://instagram.com"

# Authentication
LOGIN_URL = BASE_URL + "/accounts/login/ajax/"
LOGOUT_URL = BASE_URL + "/accounts/logout"

# Full Data Fetching
PROFILE_URL = BASE_URL + "/{username}/?__a=1"
USER_ID_URL = "https://i.instagram.com/api/v1/users/{user_id}/info/"
POST_URL = BASE_URL + "/p/{shortcode}/?__a=1"
HASHTAG_URL = BASE_URL + "/explore/tags/{tagname}/?__a=1"

# GraphQL Query URL
QUERY_URL = BASE_URL + "/graphql/query/?query_hash={0}&variables={1}"
# GraphQL Query Hashes
QUERYHASH_COMMENTS = "f0986789a5c5d17c2400faebf16efd0d"
QUERYHASH_LIKES = "e0f59e4a1c8d78d0161873bc2ee7ec44"
QUERYHASH_FOLLOWERS = "56066f031e6239f35a904ac20c9f37d9"
QUERYHASH_FOLLOWINGS = "c56ee0ae1f89cdbd1c89e2bc6b8f3d18"
QUERYHASH_REELITEMS = "cda12de4f7fd3719c0569ce03589f4c4"
QUERYHASH_HIGHLIGHTS = "7c16654f22c819fb63d1183034a5162f"
QUERYHASH_TIMELINE = "66eb9403e44cc12e5b5ecda48b667d41"
QUERYHASH_SAVED = "8c86fed24fa03a8a2eea2a70a80c7b6b"
QUERYHASH_TAGGED = "ff260833edf142911047af6024eb634a"
QUERYHASH_IGTV = "7a5416b9d9138c7a520a66f58a53132c"
QUERYHASH_HASHTAG = "f92f56d47dc7a55b606908374b43a314"
QUERYHASH_EXPLORE = "ecd67af449fb6edab7c69a205413bfa7"
# stories feed: 6fe9aa30b8b89bdd53513e64f27761b6 {"only_stories":true,"stories_prefetch":true,"stories_video_dash_manifest":false}
