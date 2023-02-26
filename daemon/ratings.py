import asyncio
from logging import getLogger

from aiohttp import web

import globals
import tasks
import utils

logger = getLogger(__name__)

async def get_rating_handler(request: web.Request):
    data = await request.json()
    task = tasks.Task(data, data['app_id'], 'ratings/get_rating', message='Getting rating data')
    globals.tasks.append(task)
    task.async_task = asyncio.ensure_future(get_rating(task, request))
    task.async_task.add_done_callback(tasks.handle_async_errors)
    return web.Response(text='ok')

async def get_rating(task: tasks.Task, request: web.Request):
    session = request.app['SESSION_API_REQUESTS']
    headers = utils.get_headers(task.data.get('api_key',''))
    url = f'{globals.SERVER}/api/v1/assets/{task.data["asset_id"]}/rating/'
    try:
        async with session.get(url, headers=headers) as resp:
            task.result = await resp.json()
    except Exception as e:
        logger.warning(str(e))
        return task.error(f'{e}')
    task.finished('Rating data obtained')


async def send_rating_handler(request: web.Request):
    data = await request.json()
    task = tasks.Task(data, data['app_id'], 'ratings/send_rating', message=f'Sending {data["rating_type"]}rating')
    globals.tasks.append(task)
    task.async_task = asyncio.ensure_future(send_rating(task, request))
    task.async_task.add_done_callback(tasks.handle_async_errors)
    return web.Response(text='ok')

async def send_rating(task: tasks.Task, request: web.Request):
    session = request.app['SESSION_API_REQUESTS']
    headers = utils.get_headers(task.data.get('api_key',''))
    url = f'{globals.SERVER}/api/v1/assets/{task.data["asset_id"]}/rating/{task.data["rating_type"]}/'
    data = {"score": task.data['rating_value']}
    try:
        async with session.put(url, data=data, headers=headers) as resp:
            task.result = await resp.json()
    except Exception as e:
        logger.warning(str(e))
        return task.error(f'{e}')
    task.finished('Rating uploaded')


async def get_bookmarks_handler(request: web.Request):
    logger.error('getting bookmarks 1')

    data = await request.json()

    task = tasks.Task(data, data['app_id'], 'ratings/get_bookmarks', message='Getting bookmarks data')
    globals.tasks.append(task)
    logger.error('getting bookmarks')
    task.async_task = asyncio.ensure_future(get_bookmarks(task, request))
    task.async_task.add_done_callback(tasks.handle_async_errors)
    return web.Response(text='ok')

async def get_bookmarks(task: tasks.Task, request: web.Request):
    session = request.app['SESSION_API_REQUESTS']
    headers = utils.get_headers(task.data.get('api_key',''))
    url=f"{globals.SERVER}/api/v1/search/?query=bookmarks_rating:1"

    try:
        async with session.get(url, headers=headers) as resp:
            task.result = await resp.json()
        logger.error('requested bookmarks')
    except Exception as e:
        logger.warning(str(e))
        return task.error(f'{e}')
    task.finished('Bookmarks data obtained')