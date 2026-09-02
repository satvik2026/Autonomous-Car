# The Course, Explained Simply

The same five answers as `COURSE_ANALYSIS.md`, but with the measurements taken
out. This is about **why each idea works** and **what you will actually see the
car do**.

---

## 1. How does the car stay on the mud and off the grass?

### The idea

The car looks at the ground just in front of it and asks one question about
every part of the picture: *is this something I can drive on?*

It sorts the ground into three kinds:

- **Plants** — grass, the lawn, the hill. **Never drive here.**
- **Hard ground** — cement, gravel. Fine to drive on.
- **Soft ground** — mud, dirt. Fine to drive on.

Then it splits the view into **left, middle and right**, gives each a score,
and drives toward the best one.

### The mistake we had to fix

The first version decided "green = grass = stay away". That sounds right, and
it is wrong here, for one simple reason:

> **Your mud course has grass growing all over it.**

If the car avoided anything with grass in it, it would refuse to drive on the
course itself. Meanwhile the neat lawn you *must* avoid is dry and yellowish —
so a simple "is it green?" test barely noticed it, and the car would have
happily driven straight onto the lawn.

### The fix, in one sentence

**The car now asks "how much of this is plants?" instead of "is there any
plant here?"**

A patch that is a third grass is a normal bit of the mud course — drive on it.
A patch that is mostly grass is the lawn or the hill — stay off. The car only
refuses when plants clearly dominate.

We also gave it a second thing to notice: **how rough the ground is**. Cement
is smooth, gravel is bumpy. Colour alone cannot tell those apart because both
look grey — but roughness tells them apart instantly.

### What you will see

- On the mud course, grass tufts and all: **the car drives normally.**
- Approaching the grass bank on one side: **it drifts away from that side.**
- Pointed straight at the lawn or the hill: **it stops, backs up, and turns
  around.** It will not "have a go".
- Near the building or a tree: **it turns away**, because a wall or a trunk is
  not ground either.

The important behaviour: when the car has **no good option**, it stops rather
than picking the least-bad direction. That is what keeps it off the hill.

### One practical thing

Mount the camera **about 15–20 cm up, tilted down slightly**. In your own
video, the camera was held low and pointing down, and the picture was just
close-up dirt — no useful information about where to go. The camera needs to
see the ground *ahead*, not the ground *underneath*.

---

## 2. Bumps, steps and ramps — should the car look for the easy way up?

### Yes. And here is the thing that makes it matter

On your course, the **same concrete edge** is impossible at one end and easy at
the other. At one point it is a sharp 6–10 cm lip. A few metres along, the dirt
has built up and it is almost flat.

So "find the easy crossing" is not a refinement. It is the difference between
finishing the course and getting stuck on your first obstacle.

### What a small car can and cannot climb

A rigid car can climb a step of roughly **a third of its wheel height** — and
only with grip and power to spare.

- Small hobby wheels (~6 cm): can manage a couple of centimetres. The flush
  edge yes. The sharp lip, no.
- Bigger wheels (~10 cm): noticeably better at everything.

**The most useful thing you can do mechanically is fit the biggest wheels that
will fit.** That helps more than any code change.

The tall retaining wall is simply **not climbable** — treat it as a wall, not
an obstacle to attempt.

### The three rules the car follows

1. **Hit it straight on.** Approach a step at an angle and one wheel lifts
   first, the car twists, and it beaches. So the car straightens up *before*
   crossing.
2. **Use momentum.** Creeping up to a step and pushing gently just stalls with
   the wheel jammed against the edge. The car gives a short burst of speed and
   goes over.
3. **Never turn while on the edge.**

For hills: **drive straight up, never across the slope.** A car like this
slides sideways downhill and can tip.

### An honest limitation you should know about

We tested whether the camera can *spot* a step by itself. **It cannot.** A 6 cm
lip looks the same to a single camera as flat ground — shadows and dry grass
create edges that look just as strong. Anyone who tells you a single webcam
reliably detects small steps is guessing.

So the car does **not** try to discover steps. Instead:

- **You tell it where the step is** — it is part of your route order, so the
  car knows a step is coming and switches into "crossing" mode.
- **Optionally**, a second cheap sensor pointed at the ground gives a real
  measurement of the step. This is the reliable way, and it costs about £2.

Because of that, the code deliberately does **nothing** when it is unsure,
rather than swerving at shadows. An earlier version steered toward the
"easiest crossing" on a perfectly flat cement slab, purely because of the way
the light fell across it. That behaviour is now removed.

### What you will see

- Approaching a kerb in crossing mode: **the car straightens, pauses briefly
  on the aim, then surges over.**
- On flat ground: **no swerving.** It goes straight.
- On a slope: **it points uphill and climbs with more power** rather than
  wandering across the face.

---

## 3. How do you decide the order of the course?

### The idea

The car has no map and no GPS. So the route is not a set of coordinates — it
is a **list of steps, in order**, like a recipe.

Each step says three things:

1. **What to do** — follow the open ground / turn around / creep / cross a step.
2. **How to know it's finished** — the ground changed to gravel, a marker came
   into view, something is close ahead, or enough time passed.
3. **What must never happen** — never drive onto plants, never hit anything.

That's the whole concept. The clever part is only in point 2: **the car can
tell what it is driving on**, so "the ground changed to gravel" is something it
can genuinely detect.

### How you write your own

Open `course/missions/demo_course.json` and list your steps in order. For each
one ask:

> *"When this part is over, what changes under the wheels?"*

That is your finishing condition. If nothing changes, use a time limit — you
cannot put anything out on this course, so a time limit is the fallback.

Your example becomes:

1. **Mud course** — follow the open ground, leaning away from the grass bank.
   Ends when something is close ahead.
2. **Turn** — a quarter turn on the spot, towards the slopes.
3. **Slopes** — climb, with extra power.
4. **Past the compost pit** — lean away from it; ends when the green sacks
   come into view.
5. **Gravel** — creep across. Ends when cement appears.
6. **Cross onto the cement** — straighten and burst over the edge.
7. **Cement run** — follow to the finish.

**Always give every step a time limit** so a missed cue can never leave the car
stuck waiting forever.

### What you will see

A running commentary as it goes:

```
[1/7] mud_course        surf=mud    steer=-0.12   t=12.4s
-> EXIT mud_course (obstacle within 0.5m)
[2/7] turn_to_slopes    ...
```

and at the end, a summary of how long each part took and what ended it. When
something goes wrong, you will know exactly which step and why.

### The one weak point

The turn is **timed**, not measured — the car has no compass, so it spins for a
set number of seconds and will be a few degrees different each run.

The good news is that a **quarter turn is far more forgiving than a half
turn**: the error grows with the angle, so it is roughly halved, and the step
that follows steers on the camera and straightens things out within a metre.
No motion sensor needed for a turn this size.

What you *do* need to do is time it on the day. Let it spin for five seconds on
the surface you will run on, count the turns, and work out the seconds per
quarter turn. Grip and battery charge both change the answer, so do it on the
day rather than trusting the number in the file.

---

## 4. How does the camera change where the car goes?

### The flow, in plain terms

Every tenth of a second:

1. Take a picture.
2. Ignore the top half — that is sky, buildings and distant trees, none of
   which the car is about to drive on.
3. Sort the remaining ground into plants / hard / soft.
4. Score the left, middle and right.
5. Cross out any side that is mostly plants — **this is the rule that keeps it
   off the lawn.**
6. Steer toward the best remaining side.

### Three things that make it behave well

- **Gentle corrections stay gentle.** The car does not jerk between hard-left
  and hard-right. If one side is *slightly* better, it eases over slightly —
  by easing off one motor, exactly as you originally designed. If one side is
  *much* better, it turns hard.
- **It prefers going straight.** On an open court it will not weave about
  hunting for a marginally better patch.
- **It refuses rather than guesses.** No good option means stop — not "pick
  the least bad and hope".

### Does the old colour method still work? No.

Three reasons, and the first one is serious:

1. **It would drive onto the lawn.** Dry lawn grass read as perfectly good
   ground. The exact thing you need to avoid was classified as drivable.
2. **It could not tell cement from mud.** Now that cement is part of the
   course, the car needs to know which zone it is in — and the old method saw
   both as identical.
3. **It refused wet mud.** After rain, the car would have stopped on ground
   that was completely fine.

### "But we need to drive *on* the hills"

This is the part worth understanding, because "avoid grass" and "climb the
grassy slope" contradict each other.

The answer: **they are not both rules all the time.**

Keep-out is decided **per step of the route**, not once and for all. The lawn
is off-limits during every step. The slope you are meant to climb is allowed
**only during the step whose job is climbing it**. During that step the car
raises its power and accepts the grass; the moment that step ends, the normal
keep-out rule returns.

### What you will see

- Wide open ground → **straight and steady.**
- Grass creeping in on one side → **a gentle, continuous drift away.**
- Grass filling the view → **stop, reverse, turn.**
- During the climbing step → **it drives up the grassy slope on purpose,**
  with more power, then goes back to avoiding grass afterwards.

---

## 5. Would saving pictures of key places work?

### Your idea was right. The obvious version of it is not.

Saving a photo of the compost pit and comparing it to what the camera sees
fails, because:

- The car will never be standing exactly where you stood.
- Sunshine and cloud change every colour in the picture.
- Your photos were taken at chest height; the car's camera is at ankle height.
  Everything is in a different place.
- Things move — people, parked scooters, the volleyball net, fallen leaves.

The dangerous failure isn't "it doesn't recognise anything". It is
**recognising the wrong place confidently** and turning into the pit.

### What works instead — three levels

**Level 1 — recognise the *surface*, not the picture.** Instead of matching
pixels, the car notices "I am on gravel now" or "this is cement". Because it
is judging the whole area rather than exact detail, it does not care where
exactly the car is standing or how bright the day is. **This is what actually
drives the route order, and it already works.**

**Level 2 — recognise landmarks by their features.** For genuinely distinctive,
unmoving things — a building corner, the retaining wall — the car stores a set
of *feature points* rather than the picture itself. This survives moving around
and changes in light far better. You need several views of each place, taken
**from the car, at the height and in the light of the real run**.

In testing this correctly recognised the compost pit from a photo it had never
seen, and correctly refused to match the cement, the lawn or the mud court —
no false alarms, which is the property that matters. It also missed one view
it had not been trained on, which is exactly why you record several.

**Level 3 — spot the brightly coloured things that are already there.**
A big patch of a strong colour is recognised almost perfectly, from any angle,
in any light. You cannot put cones or tags out on this course, but two things
are standing there anyway: the **bright green compost sacks**, right where you
need a decision, and the blue portable toilets along the trail.

The catch is not the spotting — that part is easy and reliable. It is that you
did not choose where they are, they might be moved before the day, and they are
only in view from certain angles. So they are treated as a **bonus**: if the
sacks are seen, the step ends early; if not, the time limit ends it. Never let
a step depend on them alone.

### The safety rule that makes all of this safe

**Recognising a place never steers the car.** It only ticks off a step in the
route. Steering and collision-avoidance always have the final say.

So if the car wrongly thinks it has seen the compost pit, the worst that
happens is it moves to the next step of the route too early. It cannot cause a
crash or send the car onto the lawn.

### And about the compost pit specifically

The pit is a **hole**, and this deserves emphasis: a forward-pointing distance
sensor sees **nothing at all** over a hole. It reads "all clear" right up to
the moment the car drives in. The camera cannot see into it either.

So use several defences at once:

1. Steer away from that side for the whole step,
2. Go slowly through it,
3. Use the **green sacks** as the sign that you are alongside it,
4. Keep a time limit behind the sacks, in case they have been moved,
5. **Add the small downward-pointing sensor** — over a hole the ground suddenly
   reads *further away*, or the echo does not come back at all. This is the
   only genuinely reliable detection, and the only one of the five that senses
   the pit rather than assuming where it is.

**Fit it on a small mast, about 20 cm up, tilted about 35° down** — not on the
front lip of the chassis next to the camera. Down at 3 cm it would be looking
at a patch of ground 11 cm in front of the car, which arrives before the car
could possibly stop, and that is too close for the sensor to measure anyway.
Up on a mast it watches a patch about 25 cm ahead, which at a gentle speed is
roughly half a second of warning. Keep the mast **stiff**: if it wobbles, every
bump looks like a hole.

---

## The short version

| Question | The answer in one line |
|---|---|
| Stay on the mud? | Judge *how much* plant life is there, not whether any is — your course is partly grass. |
| Steps and ramps? | Seek the flush crossing, hit it straight, use momentum — and fit bigger wheels. |
| Route order? | A recipe of steps, each ending on something the car can actually sense. |
| Camera and direction? | It scores left/middle/right and crosses out anything that is mostly plants; keep-out is per-step, so climbing a grassy slope is still allowed when that is the job. |
| Saved pictures? | Match surfaces and features, not pixels — and treat the coloured things already on site as a bonus, never the only cue. |
