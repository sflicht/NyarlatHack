return function(c)
  local s=c.state
  if s==nil or s<0 or s>1000000 then s=0 end
  local ns=s+1
  if ns>1000000 then ns=0 end
  local h=c.history
  if h==nil or h[1]==nil then return {dx=0,dy=0,state=ns} end
  if s%4==0 then return {dx=0,dy=0,state=ns} end
  local len=1
  if h[2]~=nil then len=2 end
  if h[3]~=nil then len=3 end
  if h[4]~=nil then len=4 end
  if h[5]~=nil then len=5 end
  if h[6]~=nil then len=6 end
  if h[7]~=nil then len=7 end
  if h[8]~=nil then len=8 end
  local back=0
  if s%4==1 then back=2 end
  if s%4==2 then back=1 end
  local idx=len-back
  if idx<1 then idx=1 end
  local t=h[idx]
  if t.x==c.mx and t.y==c.my then t=h[len] end
  local dx=0
  local dy=0
  if t.x>c.mx then dx=1 end
  if t.x<c.mx then dx=-1 end
  if t.y>c.my then dy=1 end
  if t.y<c.my then dy=-1 end
  return {dx=dx,dy=dy,state=ns}
end
