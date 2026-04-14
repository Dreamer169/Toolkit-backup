import { Router, type IRouter } from "express";
import healthRouter from "./health";
import toolsRouter from "./tools";
import dataRouter from "./data.js";
import agentRouter from "./agent.js";

const router: IRouter = Router();

router.use(healthRouter);
router.use(toolsRouter);
router.use(dataRouter);
router.use(agentRouter);

export default router;
