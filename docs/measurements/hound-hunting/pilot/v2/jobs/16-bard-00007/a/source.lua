return function(c)
  local s=c.state+1
  if s>1000000 then s=0 end
  -- fourth-foot hold: an older footfall mistaken for the one still arriving
  if s%4==0 then return {dx=0,dy=0,state=s} end
  local n=#c.history
  if n<1 then return {dx=0,dy=0,state=s} end
  local idx=n
  if n>1 and s%5==2 then idx=n-1 end
  local t=c.history[idx]
  if idx<n and t.x==c.mx and t.y==c.my then t=c.history[n] end
  local dx=0
  local dy=0
  if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
  if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
  return {dx=dx,dy=dy,state=s}
end
