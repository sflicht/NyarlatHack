return {
  name = 'Pale Reed',
  inspect = function(ctx)
    local s, i, c, st = ctx.sanity, ctx.insight, ctx.charges, ctx.state
    if st >= 3 and s < 45 then
      return 'Dust lines the crack. Four notes almost gather, then leave only your breath.'
    end
    if i >= 40 and st >= 1 then
      return 'The split recurs without a mark to explain it. A half-step stays missing.'
    end
    if c == 0 then
      return 'The reed is quiet. Its crack keeps a dry shine, as if a tone had stepped aside.'
    end
    if s >= 80 and st == 0 then
      return 'An ivory reed, thumb-worn at one end. The crack does not follow the grain.'
    end
    if st >= 1 then
      return 'The crack has a pale lip now. You keep waiting for a note that does not come.'
    end
    return 'The reed lies still. Its varnish is even, except where the split is too exact.'
  end,
  apply = function(ctx)
    local s, i, c, st = ctx.sanity, ctx.insight, ctx.charges, ctx.state
    local nst = st + 1
    if nst > 255 then nst = 255 end
    local phase = st % 4
    local text = 'The pale grain shifts. A measure begins, then politely declines to finish.'
    local d = -1
    if st == 0 and s >= 70 then
      text = 'You turn the reed. A dry click answers late, like a missed entrance in a quiet room.'
      d = -1
    elseif st == 0 then
      text = 'The reed is cool and ordinary, until the crack seems to answer a note you did not sound.'
      d = -1
    elseif s < 40 and st >= 2 then
      text = 'The same four notes nearly cohere. They fray before any title can be given them.'
      d = -2
    elseif i >= 80 then
      text = 'Nothing on the reed names the omission. The unfinished step simply comes again.'
      d = -1
    elseif phase == 1 and c >= 2 then
      text = 'Under your thumb a thin tone rises, elegant and brief, and then forgets itself.'
      d = 0
    elseif c <= 1 then
      text = 'The reed feels thinner. It offers one spare tone, then the crack goes dull.'
      d = 0
    elseif st >= 200 then
      text = 'Further pressure changes little. The crack keeps its old, exact, unfinished shine.'
      d = 0
    end
    return { text = text, state = nst, sanity_delta = d }
  end
}
