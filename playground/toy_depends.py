def get_current_user(token):
    if token != "secret":
        raise Exception("401: not allowed")
    return "Asha"

def history_handler(current_user):
    return f"history for {current_user}"

def profile_handler(current_user):
    return f"profile of {current_user}"

def handle_history(token):
    user = get_current_user(token)    # dependency runs first
    return history_handler(user)      # handler runs only if the line above succeeded

def handle_profile(token):
    user = get_current_user(token)    # same check, reused
    return profile_handler(user)

for token in ["secret", "wrong"]:
    try:
        print(handle_history(token))
        print(handle_profile(token))
    except Exception as e:
        print("blocked:", e)
