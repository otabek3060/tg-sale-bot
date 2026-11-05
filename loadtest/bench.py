"""Yuklama testi: N ta foydalanuvchi BIR VAQTDA to'liq xarid oqimidan o'tadi.

Haqiqiy Dispatcher + PostgreSQL + Redis; Telegram API soxta, lekin har chaqiruvga tarmoq kechikishi
qo'shiladi (default 50 ms). `--procs K` — K ta bot jarayoni (WEB_WORKERS=K ga teng), umumiy DB/Redis bilan.

    python -m loadtest.bench --users 500 --ramp 10 --think 1 3 --procs 2   # real cho'qqi (reklamadan keyin)
    python -m loadtest.bench --users 500                                    # eng og'ir: hammasi bir lahzada

DIQQAT: test bazasini (TEST_DATABASE_URL) tozalab yuboradi — ishlab chiqarish bazasida ishlatmang!
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import multiprocessing as mp
import random
import time

from sqlalchemy import func, select

from app.bot import build_app
from app.callbacks import PayCb, UserCb
from app.db.models import Payment, PaymentStatus, User
from tests.conftest import ADMIN2, OWNER, make_app, make_config
from tests.fake_tg import FakeTelegram, Sim

BASE = 100_000


def pct(data: list[float], p: float) -> float:
    s = sorted(data)
    return s[min(len(s) - 1, int(len(s) * p))]


def _uvloop() -> None:
    try:
        import uvloop  # ishlab chiqarishdagi kabi

        uvloop.install()
    except ImportError:
        pass


async def _users_phase(idx: int, procs: int, users: int, latency: float, ramp: float,
                       think: tuple[float, float]) -> tuple[list[float], float, float, int]:
    fake = FakeTelegram(latency=latency)
    app = build_app(make_config(user_rate_limit=4, receipts_per_minute=3), session=fake)
    await app.startup()
    sim = Sim(app.bot, app.dp)
    rnd = random.Random(42 + idx)
    lat: list[float] = []

    async def step(coro) -> None:  # type: ignore[no-untyped-def]
        t0 = time.perf_counter()
        await coro
        lat.append((time.perf_counter() - t0) * 1000)

    async def pause() -> None:
        if think[1]:
            await asyncio.sleep(rnd.uniform(*think))

    async def journey(i: int) -> None:
        uid = BASE + i
        if ramp:
            await asyncio.sleep(ramp * i / users)  # foydalanuvchilar `ramp` soniya ichida bir tekis kirib keladi
        await step(sim.send(uid, "/start", name=f"User{i}"))
        await pause()
        await step(sim.click(uid, UserCb(action="buy").pack()))
        await pause()
        await step(sim.send(uid, photo=f"receipt_{i}"))

    t0, c0 = time.perf_counter(), time.process_time()
    await asyncio.gather(*(journey(i) for i in range(idx, users, procs)))
    wall = time.perf_counter() - t0
    cpu = (time.process_time() - c0) / wall * 100
    await app.tasks.wait(timeout=120)
    errors = sum("nosozlik" in (getattr(c, "text", "") or "") for c in fake.calls)
    await app.shutdown()
    return lat, wall, cpu, errors


def _worker(idx: int, procs: int, users: int, latency: float, ramp: float, think: tuple[float, float],
            q: mp.Queue) -> None:
    logging.disable(logging.WARNING)
    _uvloop()
    q.put(asyncio.run(_users_phase(idx, procs, users, latency, ramp, think)))


async def _setup() -> None:
    app = await make_app(FakeTelegram())
    await app.shop.set("static_link", "https://example.com/download", OWNER)
    await app.shutdown()


async def _approve_phase(users: int, latency: float) -> bool:
    fake = FakeTelegram(latency=latency)
    app = build_app(make_config(), session=fake)
    await app.startup()
    sim = Sim(app.bot, app.dp)
    async with app.sf() as s:
        pids = list((await s.execute(select(Payment.id).order_by(Payment.id))).scalars())
    alat: list[float] = []
    sem = asyncio.Semaphore(20)  # bir vaqtda 20 ta bosish — odam tezligidan ancha yuqori

    async def race(p: int) -> None:
        async with sem:
            t0 = time.perf_counter()
            # Ikkala admin AYNAN BIR to'lovni bir vaqtda tasdiqlaydi — poyga holati sinovi
            data = PayCb(action="ok", pid=p).pack()
            await asyncio.gather(sim.click(OWNER, data), sim.click(ADMIN2, data))
            alat.append((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    await asyncio.gather(*(race(p) for p in pids))
    await app.tasks.wait(timeout=120)
    print(f"▶ {len(pids)} ta to'lovni 2 admin bir vaqtda tasdiqlashga urindi: {time.perf_counter()-t1:.1f} s, "
          f"p95={pct(alat,.95):.0f} ms")

    async with app.sf() as s:
        n_users = (await s.execute(select(func.count()).select_from(User).where(User.telegram_id >= BASE))).scalar_one()
        approved = (await s.execute(select(func.count()).select_from(Payment)
                                    .where(Payment.status == PaymentStatus.approved))).scalar_one()
        buyers = (await s.execute(select(func.count()).select_from(User).where(User.has_purchased))).scalar_one()
    links = sum("example.com/download" in (getattr(c, "text", "") or "") for c in fake.calls)
    print("▶ Tekshiruv:")
    print(f"  userlar DB'da: {n_users}/{users}   tasdiqlangan: {approved}/{users}   xaridorlar: {buyers}")
    print(f"  yuborilgan havolalar: {links} (kutilgan {users}, dublikatsiz)")
    await app.shutdown()
    return n_users == users and approved == users and links == users


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=500)
    ap.add_argument("--latency", type=float, default=0.05, help="Telegram API kechikishi, s")
    ap.add_argument("--ramp", type=float, default=0.0, help="userlar necha soniyada kirib keladi (0 = bir lahzada)")
    ap.add_argument("--think", type=float, nargs=2, default=(0.0, 0.0), help="qadamlar orasidagi pauza: min max")
    ap.add_argument("--procs", type=int, default=1, help="bot jarayonlari soni (WEB_WORKERS)")
    a = ap.parse_args()
    logging.disable(logging.WARNING)
    _uvloop()
    asyncio.run(_setup())

    mode = (f"{a.ramp:.0f} s ichida kirib keladi, qadamlar orasida {a.think[0]:.0f}–{a.think[1]:.0f} s pauza"
            if a.ramp else "HAMMASI BIR LAHZADA (eng og'ir holat)")
    print(f"▶ {a.users} user: /start → Sotib olish → chek | {mode} | Telegram {a.latency*1000:.0f} ms | "
          f"{a.procs} jarayon")
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    workers = [ctx.Process(target=_worker, args=(i, a.procs, a.users, a.latency, a.ramp, tuple(a.think), q))
               for i in range(a.procs)]
    for w in workers:
        w.start()
    results = [q.get() for _ in workers]
    for w in workers:
        w.join()

    lat = [x for r in results for x in r[0]]
    wall = max(r[1] for r in results)
    errors = sum(r[3] for r in results)
    print(f"  {len(lat)} update, {wall:.1f} s; CPU har jarayonda: " + ", ".join(f"{r[2]:.0f}%" for r in results))
    print(f"  javob vaqti: p50={pct(lat,.5):.0f} ms  p95={pct(lat,.95):.0f} ms  p99={pct(lat,.99):.0f} ms  "
          f"max={max(lat):.0f} ms   xatolar: {errors}")
    ok = asyncio.run(_approve_phase(a.users, a.latency))
    print("✅ MUVAFFAQIYATLI" if ok and errors == 0 else "❌ MUAMMO BOR")


if __name__ == "__main__":
    main()
