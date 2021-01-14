import asyncio
from collections import deque
from datetime import datetime
import json
import tornado.ioloop
import tornado.locks
import tornado.web
import tornado.websocket


def singleton(cls):
    instances = {}

    import functools

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


@singleton
class MessagesBuffer():  

    def __init__(self):
        self.cond = tornado.locks.Condition()
        self.__messages = deque(maxlen=100)
        # self.__messages = []
        # self.__messages_size = 500        


    def add_message(self, message):
        self.__messages.append(message)
        # print(self.__messages)
        # if len(self.__messages) > self.__messages_size:
        #     self.__messages = self.messages[-self.__messages_size]
        self.cond.notify_all()

    def get_messages(self):
        return self.__messages

    def get_messages_since(self, cursor):
        results = []
        for msg in reversed(self.__messages):
            if msg['id'] == cursor:
                break
            results.append(msg)
        results.reverse()
        return results


globalmessagebuffer = MessagesBuffer()


class IndexHandler(tornado.web.RequestHandler):
    # отображать какую-то индексную страницу
    def get(self):
        self.render("index.html", messages = {})


class StatHandler(tornado.web.RequestHandler):
    def get(self):
        stat = {}
        messages = globalmessagebuffer.get_messages()
        stat['all'] = len(messages)
        for m in messages:
            if m['user_id'] not in stat:
                stat[m['user_id']] = 1
            else:
                stat[m['user_id']] += 1
        # print(stat)
        self.render("stat.html", statistics = stat)


class EchoWebSocketHandler(tornado.websocket.WebSocketHandler):

    def open(self):
        import uuid
        self.current_user = uuid.uuid4()
        print('websocket is opened')

    def on_message(self, message):
        import uuid
        id = uuid.uuid4()
        # print(str(self.current_user))
        message = json.loads(message)
        new_message = {'id': str(id),  'user_id': str(self.current_user), 'to_user_id': message['to_user_id'], 'nickname': message['nickname'], 'message': message['msgtxt']}
        globalmessagebuffer.add_message(new_message)
        print(f"Message #{ new_message.get('id', 'Unknown ID') } {new_message.get('user_id', 'Unknown ID')} {new_message.get('message', 'Empty message')}")
        self.write_message(f"{new_message}")
        
    def on_close(self):
        print('websocket is closed')


class MessageUpdatesHandler(tornado.web.RequestHandler):
    """docstring for MessageUpdatesHandler"""
    async def post(self):
        cursor = self.get_argument("cursor", None)
        messages = globalmessagebuffer.get_messages_since(cursor)
        while not messages:
            self.wait_future = globalmessagebuffer.cond.wait()
            try:
                await self.wait_future
            except asyncio.CancelledError:
                return 
            messages = globalmessagebuffer.get_messages_since(cursor)
        if self.request.connection.stream.closed():
            return
        # print(f"cursor {cursor} ")
        # print(messages)
        self.write(dict(messages=messages))

    def on_connection_close(self):
        self.wait_future.cancel()


def make_app():
    return tornado.web.Application([
        (r"/", IndexHandler),
        (r"/websocket", EchoWebSocketHandler),
        (r"/message/update", MessageUpdatesHandler),
        (r"/stat", StatHandler),
    ], debug = True)


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
