return {
  name = 'Pale Fermata Case',
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    if st <= 0 then
      if c <= 0 then
        return 'The case will not open. Lacquer still holds a rest too long to be only varnish.'
      elseif s >= 80 then
        return 'A lacquered reed-case, palm-small. A hairline crack holds its rest a moment too long.'
      elseif s >= 40 then
        return 'The case is faintly warm. Its crack seems to wait on a pitch no one has offered.'
      else
        return 'Warm lacquer, a split too clean. The silence inside leans toward you, then thinks better.'
      end
    elseif st == 1 then
      if i >= 40 then
        return 'The flaw almost coheres: a pale interval, repeated, still refusing its last courtesy.'
      elseif c >= 2 then
        return 'The lid gloss repeats one small discrepancy. Begun twice. Completed never.'
      else
        return 'Less gloss now. The same unfinished rest remains, thinner, and no less exact.'
      end
    elseif st == 2 then
      if s < 40 then
        return 'The crack ticks like a missed downbeat. The miss feels arranged, though no hand shows.'
      elseif c <= 1 then
        return 'One use of gloss remains, or none. The interval thins, and the thinning is precise.'
      else
        return 'Opened twice, the case keeps the same pale rest. Elegance, then the small refusal.'
      end
    else
      if c <= 0 then
        return 'Only lacquer and the same unfinished rest. Nothing further is offered; the gap stays polite.'
      elseif i >= 200 then
        return 'You know the shape of the omission now. Knowing does not complete it. The gap remains courteous.'
      elseif s < 40 then
        return 'The missed beat has moved closer to the lid. Shutting it does not finish the rest.'
      else
        return 'Three faint rings mark the lid. None closes. Repetition has made the gap almost elegant.'
      end
    end
  end,
  apply = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    local ns = st + 1
    if st >= 255 then
      ns = 3
    elseif ns > 9 then
      ns = 3
    end
    local t
    local d
    if st <= 0 then
      if s < 40 then
        t = 'The lid lifts on a split reed. A high silence leans out, polite, and will not be kept.'
        d = -1
      else
        t = 'You lift the lid. A reed, split cleanly, keeps a silence shaped like a high unfinished note.'
        d = 0
      end
    elseif st == 1 then
      if i >= 40 then
        t = 'The split aligns, then does not. You nearly name the interval, and the name falls short.'
        d = -1
      elseif s >= 70 then
        t = 'The split aligns, then does not. For a breath the air seems tuned. The tuning declines.'
        d = -1
      else
        t = 'The reed answers a pitch you did not choose. The answer is polite, and it does not finish.'
        d = -2
      end
    elseif st == 2 then
      if s < 35 then
        t = 'The missed beat returns closer. You shut the case. The shut does not end the rest.'
        d = -2
      elseif c <= 1 then
        t = 'What remains of the interval thins to courtesy. The lid settles on an omission, not a chord.'
        d = 1
      else
        t = 'Opened again, the case offers the same pale rest. Elegance, then the small refusal.'
        d = 0
      end
    else
      if s < 35 then
        t = 'Recurrence presses the crack. You set the case down. The unfinished rest is all that remains.'
        d = -2
      elseif i >= 200 then
        t = 'The pattern is almost a phrase. Almost is all it grants. You leave the last note unmade.'
        d = -1
      elseif c <= 1 then
        t = 'A last courtesy: the gloss dulls, the interval stays. Nothing arrives to complete it.'
        d = 1
      else
        t = 'The crack repeats its discrepancy. Nothing names itself. The recurrence is quite enough.'
        d = -1
      end
    end
    return { text = t, state = ns, sanity_delta = d }
  end
}
