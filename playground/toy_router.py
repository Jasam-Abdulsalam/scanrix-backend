routes = {}                       # the "list" I kept mentioning: really a dict

def get(path):                    # this plays the role of @app.get(...)
    def register(func):
        routes[("GET", path)] = func   # store: (method, path) -> your function
        return func
    return register

@get("/health")                   # runs once, at startup
def health_check():
    return {"status": "healthy"}

@get("/ping")                     # runs once, at startup
def ping():
    return {"pong": True}

def handle_request(method, path): # what the framework does for every request
    func = routes.get((method, path))
    if func is None:
        return 404, {"detail": "Not Found"}
    return 200, func()            # call YOUR function, return its result

    
print(handle_request("GET", "/health"))
print(handle_request("GET", "/ping"))
print(handle_request("GET", "/nope"))